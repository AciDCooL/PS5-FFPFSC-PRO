"""Process control and suspension utilities for PS5 FFPFSC PRO.

Provides reliable cross-platform process tree suspension (pause) and resumption (resume),
enabling users to safely pause compression or extraction jobs before putting their PC into
sleep/standby, and resume once network storage and drives have reconnected.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path
from typing import Sequence

# ── Windows ctypes definitions for fallback when psutil is unavailable ────────
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.windll.kernel32
    _ntdll = ctypes.windll.ntdll

    _TH32CS_SNAPPROCESS = 0x00000002
    _PROCESS_SUSPEND_RESUME = 0x0800
    _PROCESS_ALL_ACCESS = 0x1F0FFF

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]


def get_process_children(parent_pid: int) -> list[int]:
    """Return all child and grandchild PIDs for a given parent PID."""
    if parent_pid <= 0:
        return []

    # 1. Try psutil if available
    try:
        import psutil
        p = psutil.Process(parent_pid)
        return [c.pid for c in p.children(recursive=True)]
    except Exception:
        pass

    # 2. Windows ctypes ToolHelp snapshot fallback
    if sys.platform == "win32":
        try:
            h_snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
            if h_snap == -1 or not h_snap:
                return []
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            children: list[int] = []
            if _kernel32.Process32FirstW(h_snap, ctypes.byref(entry)):
                while True:
                    if entry.th32ParentProcessID == parent_pid:
                        children.append(entry.th32ProcessID)
                    if not _kernel32.Process32NextW(h_snap, ctypes.byref(entry)):
                        break
            _kernel32.CloseHandle(h_snap)

            # Recursively collect grandchildren
            all_children: list[int] = list(children)
            for cpid in children:
                all_children.extend(get_process_children(cpid))
            return all_children
        except Exception:
            return []

    # 3. Unix fallback: search /proc
    children = []
    try:
        proc_dir = Path("/proc")
        if proc_dir.is_dir():
            for entry in proc_dir.iterdir():
                if entry.name.isdigit():
                    stat_file = entry / "stat"
                    try:
                        content = stat_file.read_text(errors="ignore")
                        # Field 4 in /proc/[pid]/stat is ppid
                        parts = content.split()
                        if len(parts) > 3 and int(parts[3]) == parent_pid:
                            cpid = int(entry.name)
                            children.append(cpid)
                            children.extend(get_process_children(cpid))
                    except Exception:
                        pass
    except Exception:
        pass

    return children


def suspend_process_tree(pid: int) -> bool:
    """Suspend (pause) a process and all its child processes.

    Returns True if the target process was successfully suspended.
    """
    if pid <= 0:
        return False

    # 1. Try psutil first
    try:
        import psutil
        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            try:
                child.suspend()
            except Exception:
                pass
        proc.suspend()
        return True
    except Exception:
        pass

    # 2. Windows NtSuspendProcess fallback
    if sys.platform == "win32":
        children = get_process_children(pid)
        all_pids = children + [pid]
        success = False
        for p in all_pids:
            h = _kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, p)
            if not h:
                h = _kernel32.OpenProcess(_PROCESS_ALL_ACCESS, False, p)
            if h:
                try:
                    res = _ntdll.NtSuspendProcess(h)
                    if res == 0 and p == pid:
                        success = True
                finally:
                    _kernel32.CloseHandle(h)
        return success

    # 3. Unix SIGSTOP fallback
    children = get_process_children(pid)
    for cpid in children:
        try:
            os.kill(cpid, signal.SIGSTOP)
        except OSError:
            pass
    try:
        os.kill(pid, signal.SIGSTOP)
        return True
    except OSError:
        return False


def resume_process_tree(pid: int) -> bool:
    """Resume (un-pause) a process and all its child processes.

    Returns True if the target process was successfully resumed.
    """
    if pid <= 0:
        return False

    # 1. Try psutil first
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.resume()
        for child in proc.children(recursive=True):
            try:
                child.resume()
            except Exception:
                pass
        return True
    except Exception:
        pass

    # 2. Windows NtResumeProcess fallback
    if sys.platform == "win32":
        children = get_process_children(pid)
        all_pids = [pid] + children
        success = False
        for p in all_pids:
            h = _kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, p)
            if not h:
                h = _kernel32.OpenProcess(_PROCESS_ALL_ACCESS, False, p)
            if h:
                try:
                    res = _ntdll.NtResumeProcess(h)
                    if res == 0 and p == pid:
                        success = True
                finally:
                    _kernel32.CloseHandle(h)
        return success

    # 3. Unix SIGCONT fallback
    try:
        os.kill(pid, signal.SIGCONT)
        resumed_parent = True
    except OSError:
        resumed_parent = False

    children = get_process_children(pid)
    for cpid in children:
        try:
            os.kill(cpid, signal.SIGCONT)
        except OSError:
            pass

    return resumed_parent


def check_storage_accessible(paths: Sequence[Path | str | None], timeout: float = 3.0) -> tuple[bool, str | None]:
    """Verify that all given directories/files (especially network shares) are responsive.

    Polls for up to `timeout` seconds before returning (False, unreachable_path).
    """
    valid_paths: list[Path] = []
    for p in paths:
        if p:
            valid_paths.append(Path(p))

    if not valid_paths:
        return True, None

    deadline = time.time() + max(0.5, timeout)
    while True:
        all_ok = True
        failed_path_str: str | None = None

        for p in valid_paths:
            try:
                # Check target or nearest existing parent (for files yet to be created)
                check_target = p if (p.exists() or not p.parent) else p.parent
                if not check_target.exists():
                    all_ok = False
                    failed_path_str = str(p)
                    break
                # Perform a basic stat to confirm the filesystem responds (detects disconnected SMB)
                check_target.stat()
            except (OSError, PermissionError):
                all_ok = False
                failed_path_str = str(p)
                break

        if all_ok:
            return True, None

        if time.time() >= deadline:
            return False, failed_path_str

        time.sleep(0.5)
