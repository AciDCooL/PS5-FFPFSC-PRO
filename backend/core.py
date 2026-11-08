from __future__ import annotations

import os
import re
import sys
import time
import json
import shutil
import subprocess
import threading
import queue
from pathlib import Path
from collections import deque

# ── Force UTF-8 stdio ──────────────────────────────────────────────────────────
for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# ── Application Metadata & Paths ──────────────────────────────────────────────
APP_NAME = "PS5 FFPFSC PRO"
APP_VERSION = "1.3.0"
BACKEND_NAME = "bizkut/ps5-ffpfs-cli"
MKPFS_NAME = "MkPFS"

# On Linux/Docker, use ~/.config/PS5_FFPFSC_PRO_BIZKUT or APPDATA on Windows
if sys.platform == "win32":
    _base_dir = Path(os.getenv("APPDATA", str(Path.home())))
else:
    _base_dir = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))

APP_DIR = _base_dir / "PS5_FFPFSC_PRO_BIZKUT"
PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE  = APP_DIR / "history.json"
COMPAT_FILE   = APP_DIR / "compatibility.json"
RAW_LOG_FILE  = APP_DIR / "last_run_raw.log"

COMMUNITY_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Bf2lM12ocq739q_19y_9j9qH3b-G4iN3r3b-5pQ5t7A"

TITLE_RE = re.compile(r"(PPSA\d{5}|CUSA\d{5})", re.I)
PROGRESS_RE = re.compile(r"\[[#\s]+\]\s*(?P<pct>\d+)%\s*(?P<label>.*)")

STAGE_DEFS = [
    ("Scanning Files",   "Scan"),
    ("Reading Game",     "Read"),
    ("Building Image",   "Build"),
    ("Verifying Output", "Verify"),
    ("Cleaning Up",      "Clean"),
    ("Complete",         "Done"),
]

STAGE_WEIGHTS = {
    "Scanning Files":   (0,    5),
    "Reading Game":     (5,   10),
    "Building Image":   (10,  92),
    "Verifying Output": (92,  96),
    "Cleaning Up":      (96, 100),
    "Complete":         (100, 100),
}


# ── Directory and Settings Helpers ────────────────────────────────────────────

def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def load_settings() -> dict:
    ensure_app_dir()
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data: dict) -> None:
    ensure_app_dir()
    existing = load_settings()
    existing.update(data)
    SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_history() -> list:
    ensure_app_dir()
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_history(items: list) -> None:
    ensure_app_dir()
    HISTORY_FILE.write_text(json.dumps(items[-100:], indent=2), encoding="utf-8")


def load_compat() -> list:
    ensure_app_dir()
    if COMPAT_FILE.exists():
        try:
            return json.loads(COMPAT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_compat(reports: list) -> None:
    ensure_app_dir()
    COMPAT_FILE.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")


def add_compat_report(report: dict) -> None:
    reports = load_compat()
    tid = report.get("title_id", "").strip().upper()
    if tid:
        reports = [r for r in reports if r.get("title_id", "").strip().upper() != tid]
    reports.insert(0, report)
    save_compat(reports)


# ── Formatting & Time Utilities ───────────────────────────────────────────────

def now_time() -> str:
    return time.strftime("%H:%M:%S")


def now_datetime() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def format_size(num) -> str:
    try:
        num = float(num)
    except Exception:
        return "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.2f} {unit}" if unit != "B" else f"{num:.0f} {unit}"
        num /= 1024


def format_duration(seconds) -> str:
    seconds = int(max(0, seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_eta(eta_str: str) -> str:
    if not eta_str or eta_str in ("—", "-", ""):
        return "—"
    m = re.match(r"^([0-9.]+)\s*(s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours)?$", eta_str.strip(), re.I)
    if not m:
        return eta_str
    try:
        val = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        if unit.startswith("h"):
            secs = val * 3600
        elif unit.startswith("m"):
            secs = val * 60
        else:
            secs = val
        secs = int(max(0, secs))
        h, r = divmod(secs, 3600)
        m_val, s = divmod(r, 60)
        if h > 0:
            return f"{h}h {m_val:02d}m {s:02d}s"
        elif m_val > 0:
            return f"{m_val}m {s:02d}s"
        else:
            return f"{s}s"
    except Exception:
        return eta_str


def parse_speed_bps(speed_str: str) -> float:
    if not speed_str or speed_str in ("—", "-", ""):
        return 0.0
    m = re.search(r"([0-9.]+)\s*(GB|MB|KB|B)/s", speed_str, re.I)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
        unit = m.group(2).upper()
        if unit == "GB":
            return val * (1024 ** 3)
        elif unit == "MB":
            return val * (1024 ** 2)
        elif unit == "KB":
            return val * 1024
        return val
    except Exception:
        return 0.0


def sanitize_filename(name: str) -> str:
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', name)
    sanitized = sanitized.strip('. ')
    return sanitized if sanitized else "PS5_GAME"


# ── Filesystem & Hardware Inspection ──────────────────────────────────────────

def get_free_space(path: Path) -> int:
    try:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(str(target))
        return usage.free
    except Exception:
        return 0


def folder_size(path: Path) -> int:
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except Exception:
        pass
    return total


def file_count(path: Path) -> int:
    try:
        if path.is_file():
            return 1
        return sum(1 for p in path.rglob("*") if p.is_file())
    except Exception:
        return 0


def same_drive(p1: Path, p2: Path) -> bool:
    try:
        if sys.platform == "win32":
            return Path(p1).resolve().drive.upper() == Path(p2).resolve().drive.upper()
        else:
            return Path(p1).resolve().stat().st_dev == Path(p2).resolve().stat().st_dev
    except Exception:
        return False


def estimate_peak_space_needed(source_size: int, same_drive_flag: bool) -> int:
    # Source size + Temp PFS + Finished .ffpfsc output + safety margin
    if same_drive_flag:
        return int(source_size * 2.1) + (2 * 1024 * 1024 * 1024)
    else:
        return int(source_size * 1.05) + (1024 * 1024 * 1024)


# ── Title & Game Detection ────────────────────────────────────────────────────

def is_game_folder(path: Path) -> bool:
    """Return True if path looks like a game folder."""
    if not path.is_dir():
        return False
    sce_sys = path / "sce_sys"
    return (sce_sys / "param.json").exists() or (sce_sys / "param.sfo").exists() or (path / "eboot.bin").is_file()


def find_game_folders(root: Path, max_depth: int = 3) -> list[Path]:
    """Recursively find all game subfolders under root (up to max_depth levels)."""
    found: list[Path] = []

    def _scan(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if is_game_folder(path):
            found.append(path)
            return
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _scan(child, depth + 1)
        except (PermissionError, OSError):
            pass

    _scan(root, 0)
    return found


def parse_title_id(path: Path) -> str:
    m = TITLE_RE.search(str(path))
    if m:
        return m.group(1).upper()
    try:
        for p in path.rglob("param.json"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            m = TITLE_RE.search(text)
            if m:
                return m.group(1).upper()
        for p in path.rglob("param.sfo"):
            try:
                from mkpfs.game_metadata import _parse_sfo
                sfo = _parse_sfo(p.read_bytes())
                val = sfo.get("TITLE_ID")
                if val:
                    return val.strip().upper()
            except Exception:
                pass
    except Exception:
        pass
    return "Unknown"


def guess_game_name(path: Path) -> str:
    param = path / "sce_sys" / "param.json"
    if param.exists():
        try:
            data = json.loads(param.read_text(encoding="utf-8", errors="replace"))
            loc = data.get("localizedParameters", {})
            default_lang = loc.get("defaultLanguage", "")
            title = (loc.get(default_lang, {}).get("titleName", "")
                     or loc.get("en-US", {}).get("titleName", "")
                     or next((v.get("titleName", "") for v in loc.values()
                              if isinstance(v, dict) and v.get("titleName")), ""))
            if title:
                return title.strip()
        except Exception:
            pass

    param_sfo = path / "sce_sys" / "param.sfo"
    if param_sfo.exists():
        try:
            from mkpfs.game_metadata import _parse_sfo
            sfo = _parse_sfo(param_sfo.read_bytes())
            title = sfo.get("TITLE")
            if title:
                return title.strip()
        except Exception:
            pass

    name = path.name
    name = re.sub(r"[-_]app$", "", name, flags=re.I)
    name = re.sub(r"\s*\[.*?\]\s*", " ", name)
    name = re.sub(r"-\[.*?\]", "", name)
    return name.replace("_", " ").strip(" -") or path.name


def find_artwork(path: Path):
    if path.is_file():
        return None
    for name in ["icon0.png", "pic0.png", "pic1.png"]:
        try:
            hits = list(path.rglob(name))
            if hits:
                return hits[0]
        except Exception:
            pass
    return None


def is_apr_game(path: Path) -> bool:
    if path is None or not path.is_dir():
        return False
    sce_sys = path / "sce_sys"
    return (sce_sys / "playgo-chunk.dat").exists() or (sce_sys / "playgo_chunk.dat").exists()


# ── Plugin Version Management ─────────────────────────────────────────────────

def detect_mkpfs_version() -> tuple[str, str]:
    try:
        backend_dir = Path(__file__).resolve().parent
        if (backend_dir / "mkpfs" / "__init__.py").is_file():
            r = subprocess.run([sys.executable, "-m", "mkpfs", "-V"], cwd=str(backend_dir), capture_output=True, text=True, timeout=5)
            m = re.search(r"(\d+(?:\.\d+)+)", (r.stdout or r.stderr).strip())
            if m:
                return m.group(1), "Integrated"
    except Exception:
        pass

    try:
        r = subprocess.run([sys.executable, "-m", "mkpfs", "-V"], capture_output=True, text=True, timeout=5)
        m = re.search(r"(\d+(?:\.\d+)+)", (r.stdout or r.stderr).strip())
        if m:
            return m.group(1), "System"
    except Exception:
        pass

    return "1.1.0", "Integrated"


def upgrade_mkpfs_plugin(target_version: str | None = None) -> tuple[bool, str]:
    return False, "MkPFS is statically integrated (v1.1.0); plugin overrides are disabled."


def revert_mkpfs_plugin() -> bool:
    plugin_mkpfs = PLUGINS_DIR / "mkpfs"
    if plugin_mkpfs.exists():
        shutil.rmtree(plugin_mkpfs, ignore_errors=True)
    for p in PLUGINS_DIR.glob("mkpfs-*.dist-info"):
        shutil.rmtree(p, ignore_errors=True)
    return True


# ── Archive Extraction ────────────────────────────────────────────────────────

class ExtractionCancelledError(Exception):
    """Raised when archive extraction is aborted by the user."""
    pass


class PkgExtractorNotFoundError(FileNotFoundError):
    """Raised when no compatible PS4 PKG extraction tool is found."""
    pass


class PkgExtractionError(RuntimeError):
    """Raised when PKG extraction fails."""
    pass


class PkgExtractor:
    EXTRACTOR_CANDIDATES = [
        "ProsperoPkgTool",
        "prosperopkgtool",
        "prospero-pub-cmd",
        "shadpkg",
        "orbis-pub-cmd",
        "ps4-pkg-tool",
        "pkg_pfs_tool",
    ]

    @classmethod
    def locate_tool(cls, is_ps5: bool = False) -> tuple[str, str] | None:
        """Return (tool_path, tool_type) or None if no extractor is available.
        tool_type is one of: 'ProsperoPkgTool', 'prospero-pub-cmd', 'shadpkg', 'orbis-pub-cmd', 'ps4-pkg-tool', 'pkg_pfs_tool'.
        """
        _script_dir = Path(getattr(sys, "frozen", None) and sys.executable or __file__).resolve().parent
        if _script_dir.name == "backend":
            _script_dir = _script_dir.parent

        search_dirs = [
            _script_dir / "tools",
            Path(getattr(sys, "_MEIPASS", "")) / "tools",
            APP_DIR / "tools",
        ]

        exts = [".exe", ""] if sys.platform == "win32" else ["", "-debian", "-macos", ".exe"]

        candidates = list(cls.EXTRACTOR_CANDIDATES)
        if is_ps5:
            candidates.sort(key=lambda c: 0 if c in ("ProsperoPkgTool", "prosperopkgtool", "prospero-pub-cmd") else 1)
        else:
            candidates.sort(key=lambda c: 0 if c == "shadpkg" else (1 if c == "orbis-pub-cmd" else 2))

        for name in candidates:
            for sdir in search_dirs:
                for ext in exts:
                    candidate = sdir / f"{name}{ext}"
                    if candidate.is_file():
                        return str(candidate), name

            found = shutil.which(name)
            if found:
                return found, name

        return None

    @classmethod
    def extract_pkg_metadata_files(cls, pkg_path: Path, sce_sys_dir: Path) -> None:
        """Extract outer CNT metadata files (param.json, param.sfo, icon0.png) from PKG into sce_sys_dir."""
        try:
            sce_sys_dir.mkdir(parents=True, exist_ok=True)
            with open(pkg_path, "rb") as fh:
                magic = fh.read(4)
                cnt_offset = 0
                if magic == b"\x7fFIH":
                    fh.seek(0x58)
                    cnt_offset = int.from_bytes(fh.read(8), "little")
                    if cnt_offset == 0 or cnt_offset > 500 * 1024 * 1024 * 1024:
                        fh.seek(0x10)
                        pfs_off = int.from_bytes(fh.read(8), "little")
                        fh.seek(0x18)
                        pfs_sz = int.from_bytes(fh.read(8), "little")
                        cnt_offset = pfs_off + pfs_sz
                    fh.seek(cnt_offset)
                    magic = fh.read(4)

                if magic != b"\x7fCNT":
                    return

                fh.seek(cnt_offset + 0x10)
                entry_count = int.from_bytes(fh.read(4), "big")
                fh.seek(cnt_offset + 0x18)
                entry_table_offset = cnt_offset + int.from_bytes(fh.read(4), "big")
                if entry_count == 0 or entry_count > 4096 or entry_table_offset == cnt_offset:
                    return

                for index in range(entry_count):
                    entry_base = entry_table_offset + index * 0x20
                    fh.seek(entry_base)
                    entry_id = int.from_bytes(fh.read(4), "big")
                    fh.seek(entry_base + 0x10)
                    data_offset = cnt_offset + int.from_bytes(fh.read(4), "big")
                    data_size = int.from_bytes(fh.read(4), "big")

                    if data_size == 0 or data_size > 10 * 1024 * 1024:
                        continue

                    # 0x2000 = PS5 param.json, 0x1000 = PS4 param.sfo / PS5 param.json
                    if entry_id in (0x2000, 0x1000):
                        target_file = sce_sys_dir / ("param.json" if entry_id == 0x2000 else "param.sfo")
                        if not target_file.is_file():
                            fh.seek(data_offset)
                            raw = fh.read(data_size)
                            if raw.startswith(b"\x00PSF"):
                                (sce_sys_dir / "param.sfo").write_bytes(raw)
                            elif raw.strip().startswith(b"{"):
                                (sce_sys_dir / "param.json").write_bytes(raw)
                    elif entry_id == 0x1200:
                        icon_file = sce_sys_dir / "icon0.png"
                        if not icon_file.is_file():
                            fh.seek(data_offset)
                            raw = fh.read(data_size)
                            if raw.startswith(b"\x89PNG"):
                                icon_file.write_bytes(raw)
                    elif entry_id == 0x1220:
                        pic0_file = sce_sys_dir / "pic0.png"
                        if not pic0_file.is_file():
                            fh.seek(data_offset)
                            raw = fh.read(data_size)
                            if raw.startswith(b"\x89PNG"):
                                pic0_file.write_bytes(raw)
                    elif entry_id == 0x1240:
                        pic1_file = sce_sys_dir / "pic1.png"
                        if not pic1_file.is_file():
                            fh.seek(data_offset)
                            raw = fh.read(data_size)
                            if raw.startswith(b"\x89PNG"):
                                pic1_file.write_bytes(raw)
        except Exception:
            pass

    @classmethod
    def download_shadpkg(cls, log_fn=None) -> bool:
        """Attempt to auto-download shadpkg from official GitHub releases if missing."""
        import urllib.request

        if sys.platform == "win32":
            asset_name = "shadpkg.exe"
        elif sys.platform == "darwin":
            asset_name = "shadpkg-macos"
        else:
            asset_name = "shadpkg-debian"

        url = f"https://github.com/seregonwar/ShadPKG/releases/download/v2.1.0/{asset_name}"

        _script_dir = Path(getattr(sys, "frozen", None) and sys.executable or __file__).resolve().parent
        if _script_dir.name == "backend":
            _script_dir = _script_dir.parent

        dest_dirs = [
            _script_dir / "tools",
            APP_DIR / "tools",
        ]

        for d in dest_dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
                dest_file = d / asset_name
                if log_fn:
                    log_fn("INFO", f"Downloading {asset_name} from GitHub ({url})...")
                req = urllib.request.Request(url, headers={"User-Agent": "PS5-FFPFSC-PRO"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(dest_file, "wb") as f:
                    shutil.copyfileobj(resp, f)

                if sys.platform != "win32":
                    try:
                        os.chmod(dest_file, 0o755)
                    except Exception:
                        pass

                if log_fn:
                    log_fn("OK", f"Downloaded {asset_name} successfully to {dest_file}")
                return True
            except Exception as e:
                if log_fn:
                    log_fn("WARN", f"Could not download {asset_name} to {d}: {e}")

        return False

    @classmethod
    def extract(cls, pkg_path: Path, dest_root: Path, log_fn=None, progress_fn=None,
                cancel_check=None, proc_callback=None) -> Path:
        """Extract a PS4/PS5 PKG to dest_root/<title_id_or_stem> and return extracted game directory."""
        from mkpfs.game_metadata import read_game_metadata, _parse_sfo

        meta = read_game_metadata(pkg_path)
        title_id = meta.title_id if (meta.title_id and meta.title_id != "—") else pkg_path.stem
        is_ps5 = title_id.startswith(("PPSA", "PUSA")) or meta.package_type == "PS5 PKG"

        tool_info = cls.locate_tool(is_ps5=is_ps5)
        if not tool_info:
            if log_fn:
                log_fn("INFO", "PKG extractor not found locally. Attempting automatic download of shadpkg...")
            if cls.download_shadpkg(log_fn=log_fn):
                tool_info = cls.locate_tool(is_ps5=is_ps5)

        if not tool_info:
            _script_dir = Path(getattr(sys, "frozen", None) and sys.executable or __file__).resolve().parent
            if _script_dir.name == "backend":
                _script_dir = _script_dir.parent
            tools_dir = _script_dir / "tools"
            raise PkgExtractorNotFoundError(
                f"PKG extraction requires an external extraction utility.\n\n"
                f"Please place 'ProsperoPkgTool.exe', 'shadpkg.exe', or 'prospero-pub-cmd.exe' "
                f"into the tools directory:\n{tools_dir}\n\n"
                f"or install it on your system PATH."
            )

        tool_path, tool_type = tool_info
        if log_fn:
            log_fn("INFO", f"Using PKG extractor: {tool_path} ({tool_type})")

        out_dir = dest_root / title_id
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        if tool_type.lower() in ("prosperopkgtool", "prospero-pkg-tool"):
            cmd = [tool_path, "img_extract", str(pkg_path), str(out_dir), "--passcode", "00000000000000000000000000000000", "--verbose"]
        elif tool_type in ("prospero-pub-cmd", "orbis-pub-cmd"):
            cmd = [tool_path, "pkg_extract", "--passcode", "00000000000000000000000000000000", str(pkg_path), str(out_dir)]
        elif tool_type == "shadpkg":
            cmd = [tool_path, "extract", str(pkg_path), str(out_dir)]
        elif tool_type == "ps4-pkg-tool":
            cmd = [tool_path, str(pkg_path), str(out_dir)]
        elif tool_type == "pkg_pfs_tool":
            cmd = [tool_path, "--extract", str(pkg_path), str(out_dir)]
        else:
            cmd = [tool_path, str(pkg_path), str(out_dir)]

        if log_fn:
            log_fn("INFO", f"Executing: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc_callback:
            proc_callback(proc)

        recent_lines: list[str] = []
        last_progress_time = time.time()
        for line in proc.stdout:
            if cancel_check and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                shutil.rmtree(out_dir, ignore_errors=True)
                raise ExtractionCancelledError("PKG extraction cancelled by user.")

            clean_line = line.strip()
            if not clean_line:
                continue

            recent_lines.append(clean_line)
            if len(recent_lines) > 25:
                recent_lines.pop(0)

            m = re.search(r'(\d{1,3})%', clean_line)
            if m and progress_fn:
                try:
                    pct = int(m.group(1))
                    progress_fn(min(100, max(0, pct)), clean_line)
                except Exception:
                    pass
            elif log_fn and time.time() - last_progress_time > 2.0:
                last_progress_time = time.time()
                log_fn("INFO", clean_line)

        rc = proc.wait()
        if rc != 0:
            if cancel_check and cancel_check():
                raise ExtractionCancelledError("PKG extraction cancelled by user.")
            tail_msg = "\n".join(recent_lines[-6:]) if recent_lines else ""
            err_msg = f"{tool_type} failed with exit code {rc}."
            if tail_msg:
                err_msg += f"\n\nOutput:\n{tail_msg}"
            if is_ps5:
                err_msg += (
                    f"\n\nNote for PS5 title {title_id}:\n"
                    "• PS5 Fake PKGs (FPKGs) are extracted using 'ProsperoPkgTool' (bundled) with the standard zero passcode.\n"
                    "• If this is an encrypted retail PS5 package, it cannot be decrypted on PC without console hardware SAMU keys.\n"
                    "  Dump the game directly on your jailbroken PS5 console using Itemzflow or Game Dumper as a decrypted folder (/app0/) or .exfat/.ffpkg image."
                )
            raise PkgExtractionError(err_msg)

        # Locate game_root: check for sce_sys/param.json (native PS5) or sce_sys/param.sfo (PS4)
        games = find_game_folders(out_dir)
        game_root = games[0] if games else out_dir

        for pjson in out_dir.rglob("param.json"):
            if pjson.parent.name == "sce_sys":
                game_root = pjson.parent.parent
                break

        sce_sys = game_root / "sce_sys"
        cls.extract_pkg_metadata_files(pkg_path, sce_sys)

        param_json = sce_sys / "param.json"
        param_sfo = sce_sys / "param.sfo"

        if not param_sfo.is_file() and not param_json.is_file():
            found_sfos = list(game_root.rglob("param.sfo"))
            if found_sfos:
                param_sfo = found_sfos[0]
                sce_sys = param_sfo.parent
                cls.extract_pkg_metadata_files(pkg_path, sce_sys)
                param_json = sce_sys / "param.json"
                game_root = sce_sys.parent
        if sce_sys.is_dir() and not param_json.is_file() and param_sfo.is_file():
            try:
                sfo_data = _parse_sfo(param_sfo.read_bytes())
                sfo_title_id = sfo_data.get("TITLE_ID", title_id)
                sfo_title = sfo_data.get("TITLE", meta.game_title or title_id)
                generated_json = {
                    "titleId": sfo_title_id,
                    "titleName": sfo_title,
                    "localizedParameters": {
                        "defaultLanguage": "en-US",
                        "en-US": {
                            "titleName": sfo_title
                        }
                    }
                }
                param_json.write_text(json.dumps(generated_json, indent=2), encoding="utf-8")
                if log_fn:
                    log_fn("OK", f"Generated ShadowMount sce_sys/param.json for {sfo_title_id}")
            except Exception as e:
                if log_fn:
                    log_fn("WARN", f"Could not auto-generate param.json from param.sfo: {e}")
        elif not param_json.is_file():
            try:
                generated_json = {
                    "titleId": meta.title_id or title_id,
                    "titleName": meta.game_title or title_id,
                    "localizedParameters": {
                        "defaultLanguage": "en-US",
                        "en-US": {
                            "titleName": meta.game_title or title_id
                        }
                    }
                }
                param_json.write_text(json.dumps(generated_json, indent=2), encoding="utf-8")
                if log_fn:
                    log_fn("OK", f"Generated fallback sce_sys/param.json for {meta.title_id or title_id}")
            except Exception:
                pass

        return game_root


class ArchiveExtractor:
    SUPPORTED = {".zip", ".rar", ".7z", ".pkg"}

    @staticmethod
    def extract(archive: Path, dest_root: Path, log_fn=None, progress_fn=None,
                password: str = "", candidate_passwords: list[str] | None = None,
                cancel_check=None, proc_callback=None) -> Path:
        dest = dest_root / archive.stem
        suffix = archive.suffix.lower()

        if suffix == ".pkg":
            return PkgExtractor.extract(
                archive, dest_root,
                log_fn=log_fn, progress_fn=progress_fn,
                cancel_check=cancel_check, proc_callback=proc_callback
            )

        candidates: list[str] = []
        if password and password.strip():
            candidates.append(password.strip())
        if candidate_passwords:
            for p in candidate_passwords:
                p_clean = str(p).strip()
                if p_clean and p_clean not in candidates:
                    candidates.append(p_clean)
        if not candidates:
            candidates.append("")

        total_cands = len(candidates)
        last_err: Exception | None = None

        for idx, pwd in enumerate(candidates):
            if cancel_check and cancel_check():
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                raise ExtractionCancelledError("Extraction cancelled by user.")

            masked = (pwd[:2] + "*" * (len(pwd) - 2)) if len(pwd) > 2 else ("*" * len(pwd) if pwd else "(none)")
            if log_fn:
                if total_cands > 1:
                    log_fn("INFO", f"Extracting {archive.name} (attempt {idx + 1}/{total_cands} with password: {masked})")
                else:
                    log_fn("INFO", f"Extracting {archive.name} -> {dest}" + (f" [password: {masked}]" if pwd else ""))

            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True, exist_ok=True)

            try:
                if suffix == ".zip":
                    ArchiveExtractor._zip(archive, dest, log_fn, progress_fn, pwd, cancel_check=cancel_check)
                elif suffix == ".rar":
                    ArchiveExtractor._rar(archive, dest, log_fn, progress_fn, pwd, cancel_check=cancel_check, proc_callback=proc_callback)
                elif suffix == ".7z":
                    ArchiveExtractor._sevenz(archive, dest, log_fn, progress_fn, pwd, cancel_check=cancel_check, proc_callback=proc_callback)
                else:
                    raise ValueError(f"Unsupported archive format: {archive.suffix}")

                if cancel_check and cancel_check():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    raise ExtractionCancelledError("Extraction cancelled by user.")

                game_root = ArchiveExtractor._find_root(dest)
                if log_fn:
                    if pwd:
                        log_fn("OK", f"Archive extracted successfully using password: {masked}")
                    else:
                        log_fn("OK", f"Extracted to: {game_root}")
                return game_root
            except ExtractionCancelledError:
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                raise
            except Exception as exc:
                last_err = exc
                if idx + 1 < total_cands and log_fn:
                    log_fn("WARN", f"Password attempt {idx + 1} failed: {exc}. Retrying next password in list...")

        raise RuntimeError(f"All extraction attempts failed for {archive.name}. Last error: {last_err}")

    @staticmethod
    def _zip(archive: Path, dest: Path, log_fn, progress_fn, password: str = "", cancel_check=None):
        import zipfile
        pwd_bytes = password.encode("utf-8") if password else None
        with zipfile.ZipFile(archive, "r") as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            total = len(members)
            for i, member in enumerate(members):
                if cancel_check and cancel_check():
                    raise ExtractionCancelledError("Extraction cancelled by user.")
                if progress_fn:
                    progress_fn(int(i / max(1, total) * 100), member.filename)
                zf.extract(member, dest, pwd=pwd_bytes)

    @staticmethod
    def _rar(archive: Path, dest: Path, log_fn, progress_fn, password: str = "", cancel_check=None, proc_callback=None):
        try:
            import rarfile
            with rarfile.RarFile(str(archive)) as rf:
                if password:
                    rf.setpassword(password)
                members = [m for m in rf.infolist() if not m.isdir()]
                total = len(members)
                for i, m in enumerate(members):
                    if cancel_check and cancel_check():
                        raise ExtractionCancelledError("Extraction cancelled by user.")
                    if progress_fn:
                        progress_fn(int(i / max(1, total) * 100), m.filename)
                    rf.extract(m, str(dest))
            return
        except ImportError:
            pass
        except ExtractionCancelledError:
            raise
        except Exception:
            pass

        # Fallback to unrar / 7z CLI with cancellation support
        for tool in ("unrar", "rar", "7z"):
            cli = shutil.which(tool)
            if cli:
                cmd = [cli, "x", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                else:
                    cmd.append("-p-")
                cmd.extend([str(archive), str(dest)])

                proc = None
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        errors="replace",
                        bufsize=1,
                        universal_newlines=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    if proc_callback:
                        proc_callback(proc)

                    for line in proc.stdout or []:
                        if cancel_check and cancel_check():
                            proc.terminate()
                            try:
                                proc.wait(timeout=2.0)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            raise ExtractionCancelledError("Extraction cancelled by user.")
                        line = line.rstrip()
                        if progress_fn:
                            m = re.search(r"(\d+)%", line)
                            if m:
                                progress_fn(int(m.group(1)), line)

                    code = proc.wait()
                    if cancel_check and cancel_check():
                        raise ExtractionCancelledError("Extraction cancelled by user.")
                    if code == 0:
                        return
                finally:
                    if proc and proc.poll() is None and cancel_check and cancel_check():
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    if proc_callback:
                        proc_callback(None)
        raise RuntimeError("Could not extract RAR (install rarfile or unrar CLI)")

    @staticmethod
    def _sevenz(archive: Path, dest: Path, log_fn, progress_fn, password: str = "", cancel_check=None, proc_callback=None):
        try:
            import py7zr
            kwargs = {"password": password} if password else {}
            with py7zr.SevenZipFile(str(archive), mode="r", **kwargs) as sz:
                if cancel_check and cancel_check():
                    raise ExtractionCancelledError("Extraction cancelled by user.")
                sz.extractall(path=str(dest))
                if cancel_check and cancel_check():
                    raise ExtractionCancelledError("Extraction cancelled by user.")
            return
        except ImportError:
            pass
        except ExtractionCancelledError:
            raise
        except Exception:
            pass

        for tool in ("7z", "7za", "7zr"):
            cli = shutil.which(tool)
            if cli:
                cmd = [cli, "x", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                else:
                    cmd.append("-p-")
                cmd.extend([str(archive), f"-o{dest}"])

                proc = None
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        errors="replace",
                        bufsize=1,
                        universal_newlines=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    if proc_callback:
                        proc_callback(proc)

                    for line in proc.stdout or []:
                        if cancel_check and cancel_check():
                            proc.terminate()
                            try:
                                proc.wait(timeout=2.0)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            raise ExtractionCancelledError("Extraction cancelled by user.")
                        line = line.rstrip()
                        if progress_fn:
                            m = re.search(r"(\d+)%", line)
                            if m:
                                progress_fn(int(m.group(1)), line)

                    code = proc.wait()
                    if cancel_check and cancel_check():
                        raise ExtractionCancelledError("Extraction cancelled by user.")
                    if code == 0:
                        return
                finally:
                    if proc and proc.poll() is None and cancel_check and cancel_check():
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    if proc_callback:
                        proc_callback(None)
        raise RuntimeError("Could not extract 7z (install py7zr or 7z CLI)")

    @staticmethod
    def _find_root(dest: Path) -> Path:
        for param in dest.rglob("param.json"):
            if param.parent.name == "sce_sys":
                return param.parent.parent
        items = [p for p in dest.iterdir() if p.is_dir()]
        if len(items) == 1:
            return items[0]
        return dest


# ── Game Item Model ───────────────────────────────────────────────────────────

class GameItem:
    ampr_emu: bool = False
    _pkg_icon_bytes: bytes | None = None

    def __init__(self, path: Path):
        self.path = Path(path) if path else None
        self.archive_path: Path | None = None
        self.name = guess_game_name(self.path) if self.path else "Unknown"
        self.title_id = parse_title_id(self.path) if self.path else "Unknown"
        self.size = folder_size(self.path) if self.path else 0
        self.files = file_count(self.path) if self.path else 0
        self.artwork = find_artwork(self.path) if self.path else None
        self._pkg_icon_bytes = None
        self.status = "Queued"
        self.ampr_emu = is_apr_game(self.path) if self.path else False

    @classmethod
    def from_archive(cls, archive: Path) -> "GameItem":
        obj = cls.__new__(cls)
        obj.path = None
        obj.archive_path = Path(archive)
        obj.name = archive.stem
        obj.title_id = "📦"
        obj.size = archive.stat().st_size if archive.exists() else 0
        obj.files = 0
        obj.artwork = None
        obj._pkg_icon_bytes = None
        obj.status = "Pending Extract"
        obj.ampr_emu = False
        return obj

    @classmethod
    def from_pkg(cls, pkg: Path) -> "GameItem":
        obj = cls.__new__(cls)
        obj.path = None
        obj.archive_path = Path(pkg)
        obj.size = pkg.stat().st_size if pkg.exists() else 0
        obj.files = 0
        obj.artwork = None
        obj._pkg_icon_bytes = None
        obj.status = "Pending Extract"
        obj.ampr_emu = False

        try:
            from mkpfs.game_metadata import read_game_metadata
            meta = read_game_metadata(pkg)
            obj.name = meta.game_title if meta.game_title else pkg.stem
            obj.title_id = meta.title_id if (meta.title_id and meta.title_id != "—") else "📦"
            if meta.icon_bytes:
                obj._pkg_icon_bytes = meta.icon_bytes
        except Exception:
            obj.name = pkg.stem
            obj.title_id = "📦"

        return obj

    @classmethod
    def from_exfat(cls, exfat_file: Path) -> "GameItem":
        obj = cls.__new__(cls)
        obj.path = Path(exfat_file)
        obj.archive_path = None
        obj.name = exfat_file.stem
        obj.title_id = parse_title_id(exfat_file) or "💾"
        obj.size = exfat_file.stat().st_size if exfat_file.exists() else 0
        obj.files = 1
        obj.artwork = None
        obj._pkg_icon_bytes = None
        obj.status = "Queued"
        obj.ampr_emu = False
        return obj

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title_id": self.title_id,
            "path": str(self.path) if self.path else None,
            "archive_path": str(self.archive_path) if self.archive_path else None,
            "size": self.size,
            "formatted_size": format_size(self.size),
            "files": self.files,
            "status": self.status,
            "ampr_emu": self.ampr_emu,
            "has_artwork": bool((self.artwork and self.artwork.exists()) or getattr(self, "_pkg_icon_bytes", None)),
        }


# ── Folder Scanner ────────────────────────────────────────────────────────────

def scan_path_for_items(target_path: Path) -> list[GameItem]:
    """Scan a target path (file or folder) and return a list of discovered GameItems."""
    target = Path(target_path)
    if not target.exists():
        return []

    # 1. Single disk image
    if target.is_file() and target.suffix.lower() in (".exfat", ".ffpkg"):
        return [GameItem.from_exfat(target)]

    # 2. Single PKG file
    if target.is_file() and target.suffix.lower() == ".pkg":
        return [GameItem.from_pkg(target)]

    # 3. Single archive
    if target.is_file() and target.suffix.lower() in (".zip", ".rar", ".7z"):
        return [GameItem.from_archive(target)]

    # 4. Direct PS5/PS4 game folder (has sce_sys/param.json, sce_sys/param.sfo or eboot.bin)
    if (target / "sce_sys" / "param.json").exists() or (target / "sce_sys" / "param.sfo").exists() or (target / "eboot.bin").exists():
        return [GameItem(target)]

    results: list[GameItem] = []

    # 5. Multi-item parent directory: inspect immediate subfolders
    if target.is_dir():
        for sub in sorted(target.iterdir()):
            if sub.is_dir():
                if (sub / "sce_sys" / "param.json").exists() or (sub / "sce_sys" / "param.sfo").exists() or (sub / "eboot.bin").exists() or TITLE_RE.search(sub.name):
                    results.append(GameItem(sub))
            elif sub.is_file():
                suf = sub.suffix.lower()
                if suf in (".exfat", ".ffpkg"):
                    results.append(GameItem.from_exfat(sub))
                elif suf == ".pkg":
                    results.append(GameItem.from_pkg(sub))
                elif suf in (".zip", ".rar", ".7z"):
                    results.append(GameItem.from_archive(sub))

    return results


# ── Command Builder ───────────────────────────────────────────────────────────

def build_cli_command(item: GameItem, settings: dict, app_dir: Path | None = None) -> tuple[list[str], Path, Path, Path]:
    """Build the command-line arguments to run backend/cli.py for a GameItem."""
    output_folder_str = settings.get("output_folder", "").strip()
    if not output_folder_str:
        raise ValueError("No output folder specified in settings.")

    out_root = Path(output_folder_str)
    temp_root_str = settings.get("temp_folder", "").strip()
    temp_dir = Path(temp_root_str) if temp_root_str else out_root / "_ffpfsc_temp"

    # Per-game subfolder
    if settings.get("per_game_folder", False):
        out_dir = out_root / sanitize_filename(item.name)
    else:
        out_dir = out_root

    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parent

    cmd = [sys.executable, "-m", "backend.cli"]

    # Source
    cmd.extend(["--source", str(item.path)])
    cmd.extend(["--output-dir", str(out_dir)])
    cmd.extend(["--temp-dir", str(temp_dir)])

    # Output format
    out_format = settings.get("output_format", "ffpfsc")
    if out_format in ("exfat", "ffpfsc"):
        cmd.extend(["--output-format", out_format])

    # Naming format
    naming_fmt = settings.get("naming_format", "Title ID")
    cmd.extend(["--naming-format", naming_fmt])

    # Tuning options
    comp_lvl = settings.get("compression_level", 9)
    cmd.extend(["--compression-level", str(comp_lvl)])

    cpu_cnt = settings.get("cpu_count", 0)
    if cpu_cnt > 0:
        cmd.extend(["--cpu-count", str(cpu_cnt)])

    blk_sz = settings.get("block_size", "auto")
    if blk_sz and blk_sz != "auto":
        cmd.extend(["--block-size", str(blk_sz)])

    if settings.get("keep_pfs", False):
        cmd.append("--keep-pfs")

    if settings.get("verify_output", False):
        cmd.append("--verify-output")

    if settings.get("verbose", False):
        cmd.append("--verbose")

    return cmd, repo_root, out_dir, temp_dir


# ── Process Runner & Queue Engine (Headless / Web / GUI Core) ─────────────────

def stage_from_label(label: str, raw_line: str) -> str:
    text = f"{label} {raw_line}".lower()
    first_word = label.strip().lower().split()[0] if label.strip() else ""
    if first_word in ("scan", "scanning") or "discover" in text:
        return "Scanning Files"
    if first_word in ("read", "reading", "staging") or "read" in text:
        return "Reading Game"
    if first_word in ("compress", "compressing", "pack", "packing", "write", "writing", "building") or "build" in text or "image" in text or "pfs" in text:
        return "Building Image"
    if "verif" in text:
        return "Verifying Output"
    if "clean" in text:
        return "Cleaning Up"
    if "complete" in text or "done" in text:
        return "Complete"
    return "Building Image"


class CoreProcessWorker(threading.Thread):
    def __init__(self, engine: QueueEngine, item: GameItem, cmd: list[str], cwd: Path, output_dir: Path, temp_dir: Path):
        super().__init__(daemon=True)
        self.engine = engine
        self.item = item
        self.cmd = cmd
        self.cwd = cwd
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.proc: subprocess.Popen | None = None
        self.phase = "Starting"
        self.speed = "—"
        self.stage_progress = {s: 0 for s, _ in STAGE_DEFS}
        self.final_size = 0
        self.start_time = 0.0

    def run(self):
        self.start_time = time.time()
        self.engine.log("INFO", f"── Starting: {self.item.name} ({self.item.title_id})")
        self.engine.log("INFO", f"Command: {' '.join(self.cmd)}")

        try:
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            self.proc = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )

            last_flush = time.time()
            while True:
                if self.engine.cancel_requested:
                    self._terminate()
                    self.engine.finish(False, "Cancelled by user.", " ".join(self.cmd))
                    return

                line = self.proc.stdout.readline() if self.proc and self.proc.stdout else ""
                if not line:
                    if self.proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue

                clean = line.rstrip("\r\n")
                if not clean:
                    continue

                # Match progress
                prog = PROGRESS_RE.search(clean)
                if prog:
                    pct = max(0, min(100, int(prog.group("pct"))))
                    label = prog.group("label").strip()
                    stage = stage_from_label(label, clean)

                    sp = re.search(r"@\s*([0-9.]+\s*(?:GB|MB|KB|B)/s)", label, re.I)
                    if sp:
                        self.speed = sp.group(1)

                    eta_match = re.search(r"ETA\s*([0-9a-z\s.]+)", label, re.I)
                    raw_eta = eta_match.group(1).strip() if eta_match else "—"
                    eta = format_eta(raw_eta)

                    self.stage_progress[stage] = max(self.stage_progress.get(stage, 0), pct)
                    self.phase = stage

                    # Calculate overall percentage based on stage weights
                    w_start, w_end = STAGE_WEIGHTS.get(stage, (0, 100))
                    overall_pct = max(0.0, min(100.0, w_start + (pct / 100.0) * (w_end - w_start)))

                    elapsed = format_duration(time.time() - self.start_time)
                    self.engine.status_update(stage, clean, stage, pct, overall_pct, elapsed, self.speed, eta)

                    # Log progress at 10% boundaries or 100%
                    if pct % 10 == 0 or pct == 100:
                        self.engine.log("PROGRESS", f"{stage}: {pct}% @ {self.speed} (ETA: {eta})")
                else:
                    tag = "INFO"
                    upper = clean.upper()
                    if "ERROR" in upper or "FAILED" in upper or "EXCEPTION" in upper:
                        tag = "ERROR"
                    elif "WARN" in upper:
                        tag = "WARN"
                    elif "SUCCESS" in upper or "COMPLETE" in upper:
                        tag = "OK"
                    self.engine.log(tag, clean)

            code = self.proc.wait() if self.proc else 1
            if self.engine.cancel_requested:
                self.engine.finish(False, "Cancelled by user.", " ".join(self.cmd))
                return

            if code == 0:
                # Find output file size
                out_files = list(self.output_dir.glob("*.ffpfsc")) + list(self.output_dir.glob("*.exfat"))
                if out_files:
                    latest = max(out_files, key=lambda f: f.stat().st_mtime)
                    self.final_size = latest.stat().st_size
                self.engine.finish(True, f"Successfully created package for {self.item.name}", " ".join(self.cmd), final_size=self.final_size)
            else:
                self.engine.finish(False, f"Process exited with error code {code}", " ".join(self.cmd))

        except Exception as e:
            self.engine.finish(False, f"Execution failed: {e}", " ".join(self.cmd))

    def _terminate(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


class QueueEngine:
    """Core headless batch processing queue engine with real-time events and logging."""

    def __init__(self):
        self.queue: list[GameItem] = []
        self.is_running: bool = False
        self.cancel_requested: bool = False
        self.active_worker: CoreProcessWorker | None = None

        self._batch_total = 0
        self._batch_done = 0
        self._batch_failed = 0
        self._queue_start_time: float = 0.0
        self._queue_initial_bytes: int = 0
        self._last_speed_bps: float = 0.0

        self.status = {
            "title": "Ready",
            "detail": "Queue is idle. Add games and click Start Queue.",
            "stage": "Ready",
            "stage_pct": 0,
            "overall_pct": 0,
            "speed": "—",
            "elapsed": "00:00",
            "game_eta": "—",
            "queue_eta": "—",
            "current_index": 0,
            "batch_total": 0,
            "batch_done": 0,
            "batch_failed": 0,
            "is_running": False,
            "active_game": None,
        }

        self.logs: deque[dict] = deque(maxlen=1500)
        self.event_subscribers: list[queue.Queue] = []
        self._active_extract_proc: subprocess.Popen | None = None
        self._lock = threading.RLock()

    def subscribe_events(self) -> queue.Queue:
        with self._lock:
            q = queue.Queue(maxsize=100)
            self.event_subscribers.append(q)
            return q

    def unsubscribe_events(self, q: queue.Queue):
        with self._lock:
            if q in self.event_subscribers:
                self.event_subscribers.remove(q)

    def _emit(self, event_type: str, data: dict):
        payload = {"type": event_type, "data": data, "timestamp": now_time()}
        with self._lock:
            dead = []
            for sub in self.event_subscribers:
                try:
                    sub.put_nowait(payload)
                except queue.Full:
                    dead.append(sub)
                except Exception:
                    dead.append(sub)
            for d in dead:
                if d in self.event_subscribers:
                    self.event_subscribers.remove(d)

    def log(self, tag: str, message: str):
        entry = {
            "timestamp": now_time(),
            "tag": tag,
            "message": message,
        }
        with self._lock:
            self.logs.append(entry)
        self._emit("log", entry)
        print(f"[{entry['timestamp']}] [{tag}] {message}")

    def calculate_queue_eta(self, current_overall_pct: float, current_speed_str: str) -> str:
        with self._lock:
            if not self.queue:
                return "—"

            current_item = self.queue[0]
            current_sz = getattr(current_item, "size", 0) or 0
            pct_remaining = max(0.0, min(1.0, 1.0 - (current_overall_pct / 100.0)))
            current_bytes_left = current_sz * pct_remaining

            remaining_items_bytes = sum(getattr(it, "size", 0) or 0 for it in self.queue[1:])
            total_remaining_bytes = current_bytes_left + remaining_items_bytes

            if total_remaining_bytes <= 0:
                return "00:00"

            parsed_speed = parse_speed_bps(current_speed_str)
            if parsed_speed > 0:
                if self._last_speed_bps <= 0:
                    self._last_speed_bps = parsed_speed
                else:
                    self._last_speed_bps = self._last_speed_bps * 0.7 + parsed_speed * 0.3

            effective_speed = self._last_speed_bps

            if effective_speed <= 0 and self._queue_start_time > 0 and self._queue_initial_bytes > 0:
                elapsed = time.time() - self._queue_start_time
                done_bytes = max(0, self._queue_initial_bytes - total_remaining_bytes)
                if elapsed > 5 and done_bytes > 0:
                    effective_speed = done_bytes / elapsed

            if effective_speed <= 0:
                return "Calculating…"

            eta_secs = int(total_remaining_bytes / effective_speed)
            return format_duration(eta_secs)

    def status_update(self, title: str, detail: str, stage: str, stage_pct: float, overall_pct: float,
                      elapsed: str, speed: str, eta: str):
        queue_eta = self.calculate_queue_eta(overall_pct, speed)
        with self._lock:
            self.status.update({
                "title": title,
                "detail": detail,
                "stage": stage,
                "stage_pct": int(stage_pct),
                "overall_pct": int(overall_pct),
                "speed": speed,
                "elapsed": elapsed,
                "game_eta": eta,
                "queue_eta": queue_eta,
                "is_running": self.is_running,
                "batch_total": self._batch_total,
                "batch_done": self._batch_done,
                "batch_failed": self._batch_failed,
                "current_index": self._batch_done + self._batch_failed + 1 if self.is_running else 0,
                "active_game": self.queue[0].to_dict() if self.queue else None,
            })
        self._emit("status", self.status)

    def add_path(self, path_str: str) -> list[dict]:
        path = Path(path_str.strip('"\' \t'))
        items = scan_path_for_items(path)
        added = []
        with self._lock:
            for item in items:
                self.queue.append(item)
                added.append(item.to_dict())
                self.log("OK", f"Added to queue: {item.name} ({item.title_id}) [{format_size(item.size)}]")
        self._emit("queue", self.get_queue())
        return added

    def remove_at(self, idx: int) -> bool:
        with self._lock:
            if 0 <= idx < len(self.queue):
                # If removing currently running item
                if idx == 0 and self.is_running:
                    self.cancel_queue()
                removed = self.queue.pop(idx)
                self.log("INFO", f"Removed from queue: {removed.name}")
                self._emit("queue", self.get_queue())
                return True
        return False

    def move_item(self, from_idx: int, to_idx: int) -> bool:
        with self._lock:
            if 0 <= from_idx < len(self.queue) and 0 <= to_idx < len(self.queue):
                # Don't move index 0 while active
                if (from_idx == 0 or to_idx == 0) and self.is_running:
                    return False
                item = self.queue.pop(from_idx)
                self.queue.insert(to_idx, item)
                self._emit("queue", self.get_queue())
                return True
        return False

    def clear_queue(self) -> bool:
        with self._lock:
            if self.is_running:
                # Keep active item running, clear the rest
                self.queue[1:] = []
            else:
                self.queue.clear()
        self._emit("queue", self.get_queue())
        return True

    def start_queue(self) -> tuple[bool, str]:
        with self._lock:
            if self.is_running:
                return False, "Queue is already running."
            if not self.queue:
                return False, "Queue is empty. Add games first."

            settings = load_settings()
            out_folder = settings.get("output_folder", "").strip()
            if not out_folder:
                return False, "No default output folder configured. Set one in Settings."

            self.is_running = True
            self.cancel_requested = False
            self._batch_total = len(self.queue)
            self._batch_done = 0
            self._batch_failed = 0
            self._queue_start_time = time.time()
            self._queue_initial_bytes = sum(getattr(it, "size", 0) or 0 for it in self.queue)
            self._last_speed_bps = 0.0

        threading.Thread(target=self._run_next_in_queue, daemon=True).start()
        return True, "Queue started."

    def _run_next_in_queue(self):
        with self._lock:
            if not self.queue or not self.is_running or self.cancel_requested:
                self._finish_batch()
                return

            item = self.queue[0]
            settings = load_settings()

        item.status = "Running"
        self._emit("queue", self.get_queue())

        # If item is archive, extract it first
        if item.archive_path and item.archive_path.exists():
            item.status = "Extracting"
            self._emit("queue", self.get_queue())
            self.status_update(f"Extracting {item.name}", f"Unpacking archive: {item.archive_path.name}", "Reading Game", 0, 5, "00:00", "—", "—")
            try:
                temp_dir = Path(settings.get("temp_folder", str(Path(settings.get("output_folder", ".")) / "_ffpfsc_temp")))
                passwords = settings.get("archive_passwords", [])

                def _cancel_chk():
                    with self._lock:
                        return self.cancel_requested

                def _proc_cb(p):
                    with self._lock:
                        self._active_extract_proc = p

                game_root = ArchiveExtractor.extract(
                    item.archive_path, temp_dir,
                    log_fn=self.log,
                    candidate_passwords=passwords,
                    cancel_check=_cancel_chk,
                    proc_callback=_proc_cb,
                )
                if self.cancel_requested:
                    raise ExtractionCancelledError("Extraction cancelled by user.")

                item.path = game_root
                item.size = folder_size(game_root)
                item.files = file_count(game_root)
                item.name = guess_game_name(game_root)
                item.title_id = parse_title_id(game_root)
                item.status = "Running"
                self._emit("queue", self.get_queue())
            except ExtractionCancelledError:
                self.log("WARN", f"Extraction cancelled for {item.name}.")
                item.status = "Cancelled"
                self._finish_batch()
                return
            except Exception as e:
                if self.cancel_requested:
                    self.log("WARN", f"Extraction cancelled for {item.name}.")
                    item.status = "Cancelled"
                    self._finish_batch()
                    return
                self.log("ERROR", f"Extraction failed for {item.name}: {e}")
                self.finish(False, f"Extraction failed: {e}", "")
                return
            finally:
                with self._lock:
                    self._active_extract_proc = None

        try:
            cmd, repo_root, out_dir, temp_dir = build_cli_command(item, settings)
        except Exception as e:
            self.log("ERROR", f"Build command failed for {item.name}: {e}")
            self.finish(False, str(e), "")
            return

        worker = CoreProcessWorker(self, item, cmd, repo_root, out_dir, temp_dir)
        self.active_worker = worker
        worker.start()

    def finish(self, success: bool, msg: str, last_cmd: str, final_size: int = 0):
        completed_item = None
        with self._lock:
            if self.queue:
                completed_item = self.queue.pop(0)
                completed_item.status = "Done" if success else "Failed"

            if success:
                self._batch_done += 1
                self.log("SUCCESS", f"✓ {completed_item.name if completed_item else 'Game'} completed: {msg}")
                # Auto clear temp if configured
                settings = load_settings()
                if settings.get("auto_clear_temp", False):
                    tp = Path(settings.get("temp_folder", ""))
                    if tp.exists():
                        for p in tp.glob("tmp*"):
                            if p.is_dir():
                                shutil.rmtree(p, ignore_errors=True)
                # Add to history
                if completed_item:
                    add_history_entry = {
                        "date": now_datetime(),
                        "name": completed_item.name,
                        "title_id": completed_item.title_id,
                        "orig_size": completed_item.size,
                        "final_size": final_size,
                        "success": True,
                    }
                    hist = load_history()
                    hist.insert(0, add_history_entry)
                    save_history(hist)
            else:
                self._batch_failed += 1
                self.log("ERROR", f"✗ {completed_item.name if completed_item else 'Game'} failed: {msg}")

        self._emit("queue", self.get_queue())

        # Advance to next item if still running
        if self.is_running and not self.cancel_requested and self.queue:
            time.sleep(0.5)
            threading.Thread(target=self._run_next_in_queue, daemon=True).start()
        else:
            self._finish_batch()

    def _finish_batch(self):
        with self._lock:
            self.is_running = False
            self.cancel_requested = False
            self.active_worker = None
            self._queue_start_time = 0.0
            self._last_speed_bps = 0.0
            done = self._batch_done
            failed = self._batch_failed
            total = self._batch_total
            self.status.update({
                "title": "Batch Finished",
                "detail": f"Completed {done}/{total} game(s). Failed: {failed}.",
                "stage": "Complete" if failed == 0 else "Finished with errors",
                "stage_pct": 100 if failed == 0 else 0,
                "overall_pct": 100 if failed == 0 else 0,
                "game_eta": "—",
                "queue_eta": "—",
                "is_running": False,
                "active_game": None,
            })
        self._emit("status", self.status)
        self.log("INFO", f"🏁 Queue finished. Succeeded: {done}, Failed: {failed}")

    def cancel_queue(self) -> tuple[bool, str]:
        with self._lock:
            if not self.is_running and not self.active_worker and not self._active_extract_proc:
                return False, "Queue is not running."
            self.cancel_requested = True
            self.log("WARN", "Cancellation requested by user.")
            if self._active_extract_proc and self._active_extract_proc.poll() is None:
                try:
                    self.log("WARN", "Terminating active archive extraction process...")
                    self._active_extract_proc.terminate()
                except Exception:
                    pass
            if self.active_worker:
                self.active_worker._terminate()
        return True, "Cancelling queue..."

    def get_state(self) -> dict:
        with self._lock:
            st = dict(self.status)
            st["queue_count"] = len(self.queue)
            st["queue"] = [it.to_dict() for it in self.queue]
            return st

    def get_queue(self) -> list[dict]:
        with self._lock:
            return [it.to_dict() for it in self.queue]

    def get_logs(self, limit: int = 200) -> list[dict]:
        with self._lock:
            return list(self.logs)[-limit:]

    def browse_filesystem(self, target_path_str: str | None = None) -> dict:
        """Browse filesystem folders and files for container/web UI file picking."""
        if not target_path_str:
            if sys.platform == "win32":
                target = Path(os.environ.get("USERPROFILE", "C:\\"))
            else:
                # Default to /games or /output if present in container, else /
                if Path("/games").is_dir():
                    target = Path("/games")
                elif Path("/data").is_dir():
                    target = Path("/data")
                else:
                    target = Path.home()
        else:
            target = Path(target_path_str).resolve()

        if not target.exists():
            target = Path.home()

        entries = []
        try:
            if target.is_dir():
                for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    try:
                        is_dir = item.is_dir()
                        entries.append({
                            "name": item.name,
                            "path": str(item),
                            "is_dir": is_dir,
                            "size": format_size(item.stat().st_size) if not is_dir else "",
                            "is_game_candidate": is_dir or item.suffix.lower() in (".zip", ".rar", ".7z", ".pkg", ".exfat", ".ffpkg"),
                        })
                    except (PermissionError, OSError):
                        pass
        except Exception as e:
            return {"current": str(target), "parent": str(target.parent), "error": str(e), "entries": []}

        # Common roots
        roots = []
        if sys.platform == "win32":
            import string
            for letter in string.ascii_uppercase:
                drive_p = Path(f"{letter}:\\")
                if drive_p.exists():
                    roots.append({"name": f"{letter}:", "path": f"{letter}:\\"})
        else:
            roots.append({"name": "Root (/)", "path": "/"})
            roots.append({"name": "Home (~)", "path": str(Path.home())})
            for common in ("/games", "/data", "/output", "/temp", "/mnt", "/media"):
                if Path(common).exists():
                    roots.append({"name": common, "path": common})

        return {
            "current": str(target),
            "parent": str(target.parent) if target.parent != target else None,
            "entries": entries,
            "roots": roots,
        }

