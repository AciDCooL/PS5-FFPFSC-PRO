# PS5-FFPFSC-PRO — AI Operational Guide & Lessons Learned

This document serves as the persistent knowledge base and operational rulebook for AI coding assistants working on the **PS5-FFPFSC-PRO** repository. Review these mandates and architectural patterns before making modifications.

---

## 1. Core Mandates & Git Workflow

1. **Branch Workflow (Strict)**:
   - NEVER push directly to `main`.
   - Always work on the `dev` branch (`git checkout dev`).
   - Push to `origin/dev` and open a Pull Request when changes are complete.
2. **Context & Token Economy**:
   - Keep log queries and search outputs surgical. Never dump raw massive files or unfiltered process stdout.
   - Clean up all temporary scripts, test archives, or mock dumps from `/tmp` immediately after verification.
3. **Always Validate Solutions**:
   - Compile all modified Python files (`python3 -m py_compile ...`).
   - Run a static undefined name check (`python3 -m pyflakes ...`) to catch closure and scope traps.
   - Test headless/CLI mode and verify WebUI daemon endpoints when touching backend components.

---

## 2. Architecture & Dual-Mode Execution

The repository maintains a strict **DRY (Don't Repeat Yourself)** architecture supporting two presentation layers backed by a shared business engine:

```
                          ┌─────────────────────────────┐
                          │   PS5_FFPFSC_PRO_v1.3.0.py   │  (Desktop Tkinter / CustomTkinter GUI)
                          └──────────────┬──────────────┘
                                         │
┌────────────────────────┐               │  Consumes shared logic
│     backend/web.py     ├───────────────┤  (zero divergence)
│  (REST API + WebUI)    │               │
└───────────┬────────────┘               ▼
            │               ┌─────────────────────────────┐
            └──────────────►│       backend/core.py       │  (Headless QueueEngine, Scanner,
                            │  (Shared Engine & Models)   │   ArchiveExtractor, Settings)
                            └──────────────┬──────────────┘
                                           ▼
                            ┌─────────────────────────────┐
                            │       backend/cli.py        │  (MkPFS wrapper & compression execution)
                            └─────────────────────────────┘
```

### Headless & Container Isolation (Critical Lesson)
- In Linux containers and server environments, `$DISPLAY` is absent and `tkinter` is not installed.
- Unconditional top-level `import tkinter` or `import customtkinter` causes an immediate `ModuleNotFoundError` before CLI argument parsing can run.
- **Rule**: Always inspect `sys.argv` for `--web` / `--headless` and check `os.environ.get("DISPLAY")` before importing GUI modules. Use dummy widget stubs for class definitions if imported in headless mode.

---

## 3. Unattended Batch Processing & Queue Invariance

> **Cardinal Rule**: *"The Queue Must Never Stop."*
> Once the user clicks **Start Queue**, the application is unattended. It must never freeze waiting for human interaction.

### Lessons Learned & Guard Rules:
1. **APR / AMPR Game Detection**:
   - Games with `playgo-chunk.dat` are auto-detected as APR.
   - **Never prompt in batch mode**: In `_batch_auto_start()`, never call modal question dialogs (`_ask_is_apr()`). If auto-detection finds nothing, treat the game as standard unless the user explicitly toggled it in the queue list before starting.
   - Keep `disable_ampr_prompt` defaulted to `True` in settings so fresh installs do not prompt.
   - If an APR title needs emu files and the emu folder is not configured, log a warning and skip injection. Do NOT open `_ensure_ampr_folder()` modal file dialogs during batch runs.
2. **Disk Space Diagnostics**:
   - Never show `SpaceDiagnosticsDialog` (`wait_window`) during batch execution. If free space on the temp drive is low, log a warning (`WARN: Low space for <game>... Continuing batch...`) and proceed.
3. **Fault-Tolerant Auto-Advance**:
   - If a single game fails (archive extraction failure, CLI execution error, or MemoryError / OOM):
     - Pop the failed game from `self.queue` and mark it `"Failed"`.
     - Append to `self._batch_failed_items`.
     - Increment `self._batch_failed += 1`.
     - If games remain in the queue, immediately schedule `_batch_auto_start()` to process the next title.
     - Never terminate the entire batch queue (`_batch_running = False`) due to an isolated item failure.
4. **Post-Batch Modal Suppression**:
   - Suppress the post-compression community report dialog (`_prompt_compat_share`) when running batches (`_batch_total > 1`). Batch results are persisted to local history without interrupting the user.

---

## 4. Archive Extraction & Process Cancellation

Archive extraction (`.zip`, `.rar`, `.7z`) can take tens of minutes and unpack up to 100 GB. 

### Why Cancellation Failed Previously:
- Setting `self.cancel_requested = True` had no effect because `ArchiveExtractor.extract()` had no cancellation hook.
- Synchronous child processes (`7z.exe`, `unrar.exe`, or `rarfile.extractall()`) ran to completion regardless of UI state.
- Incomplete extractions left gigabytes of corrupted partial files in `_ffpfsc_temp/_extracted/`.

### The Extraction Cancellation Standard:
1. **Pass `cancel_check` and `proc_callback`**:
   `ArchiveExtractor.extract()` must accept `cancel_check: Callable[[], bool]` and `proc_callback: Callable[[subprocess.Popen], None]`.
2. **Immediate Process Termination**:
   - Any spawned CLI extractor (`7z`, `rar`, `unrar`) must register its `Popen` instance in `self._active_extract_proc`.
   - When **Cancel** is triggered, `proc.terminate()` (and fallback `proc.kill()`) is called immediately.
3. **Interruptible Python Loops**:
   - In `_zip`, `rarfile`, and `py7zr`, evaluate `cancel_check()` between individual members and raise `ExtractionCancelledError`.
4. **Debris Cleanup**:
   - When `ExtractionCancelledError` is raised, delete the destination folder (`shutil.rmtree(dest, ignore_errors=True)`) to release disk space.
5. **UI & Queue State Reset**:
   - On cancellation, mark item as `"Cancelled"`, halt batch advancement, re-enable **Start**, and disable **Cancel**.

---

## 5. Queue-Wide Real-Time ETA Engine

Users processing batches require an overall ETA for the entire queue, not just the currently compressing title:

- **Formula**:
  $$\text{Total Remaining Bytes} = \text{Current Item Remaining Bytes} + \sum \text{Upcoming Item Sizes}$$
- **Smoothing**:
  Raw transfer rates fluctuate. Parse speed strings using `parse_speed_bps(speed_str)` and apply Exponential Moving Average (EMA):
  $$\text{EMA}_{\text{speed}} = 0.70 \times \text{EMA}_{\text{prev}} + 0.30 \times \text{Speed}_{\text{current}}$$
- **Display**:
  Propagate smoothed queue ETA across the Left Sidebar, Header Badge, Overall Progress Card, and Stats Tab.

---

## 6. Python Closure & Scope Traps (Static Analysis Standard)

When refactoring large GUI codebases, beware of these subtle Python runtime errors:

1. **Cross-Method Settings Reference**:
   - If settings are loaded in `App._setup()` via `settings = load_settings()`, attach them to `self.settings`. Never attempt to read a local `settings` variable inside `App._build()` without resolving `settings = getattr(self, "settings", None) or load_settings()`.
2. **Exception Variable Deletion**:
   - In `except Exception as exc:`, Python deletes `exc` from the local scope once the `except` block completes.
   - **Bug**: `root.after(0, lambda: messagebox.showerror(..., exc))` -> `NameError: name 'exc' is not defined`.
   - **Fix**: Bind as a default argument: `root.after(0, lambda m=str(exc): messagebox.showerror(..., m))`.
3. **Inner Scope Variable Shadowing**:
   - In loop callbacks (e.g. `def _post(r=report):`), ensure the surrounding scope references `report` rather than `r`.
4. **Always run pyflakes**:
   Run `python3 -m pyflakes PS5_FFPFSC_PRO_v1.3.0.py backend/*.py | grep "undefined name"` to catch these before shipping.

---

## 7. Component Architecture & MkPFS Standard

- **Static MkPFS Integration (v1.1.0+)**: `mkpfs` is integrated statically into `backend/mkpfs/` with dependencies (`zlib-ng>=0.5.1`, `isal>=1.0.0`, `cryptography>=47.0.0`) pinned in `requirements.txt`. Do NOT use dynamic runtime plugin loading (`plugins/` folder via `--no-deps`) as compiled C-extensions fail when external wheels are loaded dynamically without native binaries.
- **Output Preservation**: Always pass `--no-adjust-output-file-extension` when invoking MkPFS `pack folder` or `pack file` so output filenames are never mutated unexpectedly.
- **Silent Startup Checks**: Never display intrusive popups on startup for component updates. Check GitHub silently in a background thread; if an update exists, update the Settings button badge (`⚙ Settings ●`) and log an informative message.

---

## 8. PlayStation Package (.pkg) Handling & ShadowMount Compatibility

The application natively supports `.pkg` files alongside archives (`.zip`, `.rar`, `.7z`) and disk images (`.exfat`, `.ffpkg`).

### PS5 Retail PKG vs. PS4 PKG Technical Distinction
- **PS5 Retail PKGs (`PPSA...`, `PUSA...`)**:
  - Hardware-encrypted using Sony Prospero SAMU keys.
  - PC extraction is mathematically impossible without console keys.
  - The app must immediately catch `title_id.startswith(("PPSA", "PUSA"))` and guide the user to dump decrypted folders (`/app0/`) or containers directly on their jailbroken PS5 using Itemzflow or Game Dumper.
- **PS4 PKGs (`CUSA...`, Fake PKGs / FPKGs)**:
  - Unpackable on PC using standard test keys / zero passcode (`00000000000000000000000000000000`).
  - Extracted using tools in `tools/` or PATH (`orbis-pub-cmd`, `ps4-pkg-tool`, `shadpkg`, `pkg_pfs_tool`).

### Key Implementation Patterns:
1. **Zero-Wait Metadata Parsing**:
   - `backend/mkpfs/game_metadata.py` (`read_game_metadata`) reads Title ID, Game Title, and `icon0.png` directly from PKG headers in pure Python without unpacking the package.
   - When added to the queue, `GameItem.from_pkg(pkg)` displays title, Title ID, and artwork immediately.
2. **External Tool Discovery (`PkgExtractor.locate_tool`)**:
   - Scans `tools/` in script/app dir, `APP_DIR/tools`, and system PATH.
   - If missing, raises `PkgExtractorNotFoundError` explaining which utility to place in `tools/`.
3. **ShadowMount Compatibility & `param.json` Auto-Synthesis**:
   - PS4 PKGs contain `sce_sys/param.sfo` but lack PS5 `sce_sys/param.json`.
   - ShadowMount on PS5 requires `param.json` to mount and index the title in the PS5 home menu.
   - `PkgExtractor.extract()` automatically parses `param.sfo` and writes a clean `sce_sys/param.json` into the extracted game root prior to packing into `.ffpfsc`.
4. **Streaming Cancellation & Progress**:
   - Subprocess lines are regex-parsed for `\d+%` to provide real-time UI progress updates.
   - Fully interruptible via `cancel_check` and `proc_callback`, cleanly killing the extractor process and deleting partial output directories upon user cancellation.

