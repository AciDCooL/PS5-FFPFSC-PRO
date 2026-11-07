
<h1 align="center">🚀 PS5 FFPFSC PRO</h1>

<p align="center">
  PS5 Game Compression Utility
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-Supported-blue">
  <img src="https://img.shields.io/badge/Linux-Supported-yellow">
  <img src="https://img.shields.io/badge/macOS-Supported-lightgrey">
  <img src="https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white">
  <img src="https://img.shields.io/badge/WebUI-Included-22c55e">
  <img src="https://img.shields.io/badge/Backend-MkPFS%20%2B%20FFPFSC-orange">
  <img src="https://img.shields.io/badge/Version-v1.3.0-green">
</p>

<p align="center">
  <a href="https://github.com/KINGDKAK/PS5-FFPFSC-PRO/releases">📥 Download</a> •
  <a href="https://youtube.com/@KINGDKAK">📺 YouTube</a> •
  <a href="https://ko-fi.com/KINGDKAK">☕ Ko-fi</a>
</p>

---

## 📦 About

PS5 FFPFSC PRO is a cross-platform GUI for compressing PlayStation 5 game dumps using MkPFS and FFPFSC.

The application supports Windows, Linux, and macOS.

The goal is simple: make PS5 game compression easy without requiring command-line tools or complicated setup.

Whether you're compressing a single game, batch processing multiple titles, or browsing community compatibility reports, everything can be done from one interface.

---

## 🖼️ Screenshots

### Main Window

![PS5 FFPFSC PRO Main Window](screenshots/main-window.png)

### Community Compatibility Database

![Community Database](screenshots/community-database.png)


### Compression Progress

![Compression Progress](screenshots/compression-progress.png)

---

## ✨ Features

* **Desktop GUI & Responsive WebUI**: Native CustomTkinter desktop interface or modern in-browser WebUI with real-time SSE streaming.
* **Headless & Container-Ready**: Run in Docker, Unraid, TrueNAS, or headless Linux servers via `--headless` or `--web`.
* **Server File Explorer**: In-browser filesystem navigator to browse and select games from mounted volumes.
* **Queue-Wide Real-Time ETA Engine**: Calculates remaining time across the entire batch based on live throughput and remaining bytes with EMA smoothing.
* **True Batch Processing**: Non-blocking auto-advance with fault tolerance (failed items don't interrupt the queue).
* **Multi-Password Archive Retry**: Automatic fallback across priority password lists for encrypted ZIP, RAR, and 7z dumps.
* **Custom Output Naming**: Choose between `Title ID` (e.g. `PPSA01234.ffpfsc`) or sanitized `Game Name` (e.g. `Astro_Playroom.ffpfsc`).
* **Modular MkPFS Plugin Architecture**: Independently updatable MkPFS plugin with one-click in-app upgrader and fallback to bundled copy.
* **Compress PS5 game dumps into .ffpfsc or raw .exfat**
* **Supports game folders, .exfat, .ffpkg, .zip, .rar, and .7z**
* **Drag-and-drop support** (Desktop mode)
* **Dedicated Options & Settings Modal**: Streamlined, uncluttered main screen with expanded queue view.
* **Privacy & Network Controls**: Opt-out of community prompts or run in strict offline mode.
* **Compression tuning options**: Sliders for compression levels (0-9), CPU cores (0=auto), and block size selection.
* **Automatic update checker & Community Database link**
* **Detailed logs and progress tracking**
* **Per-game output folders**
* **APR / AMPR game support** with PlayGo chunk detection and automatic index generation
---

## 📂 Supported Inputs

* PS5 game folders (`/app0/` format with `sce_sys/param.json` or `eboot.bin`)
* PlayStation `.pkg` packages (PS4 PKGs extracted and synthesized with `sce_sys/param.json` for ShadowMount)
* `.exfat` disk images
* `.ffpkg` containers
* `.zip` archives
* `.rar` archives
* `.7z` archives

> **Note on PKGs**: PS4 PKG extraction utilizes utilities in the `tools/` folder (such as `orbis-pub-cmd`, `ps4-pkg-tool`, or `shadpkg`). PS5 retail PKGs (`PPSA...`) are encrypted with Sony SAMU hardware keys and must be dumped directly on a jailbroken console as decrypted folders or containers.

---

## 🌐 Community Compatibility Database

After a successful compression, you can optionally submit your results to the community database.

The database allows users to:

* Share compatibility reports
* Report Working / Partial / Not Working / Not Tested Yet status
* Search by game name
* Search by Title ID
* View report counts
* View ShadowMount version information
* Browse compatibility reports directly from the application
* Duplicate submission protection
* Vote-based reporting system
* Submit results directly from the application
* Filter by compatibility status
* Browse over 5,000+ community compatibility reports

Compatibility status is vote-based so one incorrect report cannot override community results.

View the live compatibility database:

https://docs.google.com/spreadsheets/d/1dgu0p7U2yB_mhcUELz-Wkc7Yhs-avoWLY1Gcm0n5XJw/edit?usp=drive_web&ouid=115958744890792485831

Or access it directly from PS5 FFPFSC PRO.

---

## ⚙️ Compression Tuning

Advanced users can fine-tune compression using:

* Compression level selection
* CPU core selection
* Block size selection

Available block sizes:

* Auto
* Auto-Fit
* 16384
* 32768
* 65536

Smaller block sizes may improve results for games containing large numbers of small files.

Compression Presets
* 🚀 Fast
* ⚖️ Balanced
* 🗜️ Max Compression
* 💾 Low RAM

Presets automatically configure compression level, CPU cores, and block size.

---

## 🎮 AMPR / APR Support

PS5 FFPFSC PRO can detect games that require the AMPR emulator.

Features include:

* Automatic PlayGo chunk detection
* Automatic APR title detection
* Automatic AMPR index generation
* Dedicated AMPR folder configuration
* Compatibility reporting support
* Batch mode support

---

📊 Monitoring & Automation


* Live RAM meter
* Automatic update checking
* Windows completion notifications
* Automatic retry on memory errors
* Real-time progress tracking


---

🎓 User Experience


* Interactive feature tour
* What's New dialog after updates
* Full Help / FAQ section
* Detailed logging
* Resizable log panel
* Compact mode



---

## 🚀 Getting Started

### Option A: Desktop GUI (Windows / macOS / Linux with X11)

1. Download the latest release or clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python PS5_FFPFSC_PRO_v1.3.0.py
   # Or run RUN.bat on Windows
   ```
4. Add your game folders or archives to the queue, adjust your settings in **Options & Settings**, and click **▶ START QUEUE**.

---

### Option B: WebUI Mode (Local or Remote Browser)

You can run PS5 FFPFSC PRO as a lightweight, zero-dependency web application accessible from any modern browser on your local network:

```bash
# Start WebUI on default port 8080
python PS5_FFPFSC_PRO_v1.3.0.py --web

# Or specify custom host and port
python PS5_FFPFSC_PRO_v1.3.0.py --web --host 0.0.0.0 --port 8080
```

Once running, navigate to `http://localhost:8080` (or your server's IP address) in your browser.

**WebUI Features:**
* **Real-Time Streaming**: Server-Sent Events (SSE) stream live progress bars, speed, ETAs, and terminal logs directly to your browser.
* **Server File Browser**: Click `📁 Browse` to visually navigate and select folders and games directly from your server's storage without manually typing paths.
* **Queue Management**: Add, remove, reorder, and monitor batch jobs from your desktop, laptop, tablet, or phone.
* **Full Settings Modal**: Configure compression levels, CPU cores, block sizes, default folders, and archive passwords.

---

### Option C: Docker & Headless Container Deployment

PS5 FFPFSC PRO includes container support for running 24/7 on Unraid, TrueNAS, Kubernetes, or any Docker host.

#### Using Docker Compose (Recommended)

1. Clone or download the repository.
2. Edit [`docker-compose.yml`](docker-compose.yml) with your host volume paths:
   ```yaml
   services:
     ps5-ffpfsc-pro:
       build: .
       container_name: ps5-ffpfsc-pro
       restart: unless-stopped
       ports:
         - "8080:8080"
       environment:
         - HOST=0.0.0.0
         - PORT=8080
       volumes:
         - ./config:/config          # Application settings & history
         - /path/to/dumps:/games:ro  # Read-only source game dumps
         - /path/to/output:/output   # Finished .ffpfsc output
         - /path/to/temp:/temp       # High-speed scratch drive
   ```
3. Start the container:
   ```bash
   docker compose up -d --build
   ```
4. Open `http://<your-server-ip>:8080` in your web browser.

#### Using Docker CLI

```bash
# Build the image
docker build -t ps5-ffpfsc-pro .

# Run the container
docker run -d \
  --name ps5-ffpfsc-pro \
  -p 8080:8080 \
  -v /path/to/config:/config \
  -v /path/to/games:/games:ro \
  -v /path/to/output:/output \
  -v /path/to/temp:/temp \
  ps5-ffpfsc-pro
```

> [!NOTE]
> When running on a headless Linux environment without an active `$DISPLAY` or `$WAYLAND_DISPLAY`, running `python PS5_FFPFSC_PRO_v1.3.0.py` will automatically detect the headless environment and launch the WebUI rather than crashing on missing X11/Tkinter libraries.

---

## ⏱️ Queue-Wide Real-Time ETA Engine

Unlike tools that only show the ETA for the active stage of the currently running game, PS5 FFPFSC PRO features an intelligent **Queue-Wide ETA Engine**:

$$\text{Remaining Bytes} = (\text{Current Game Size} \times (1 - \text{Game Progress})) + \sum (\text{Remaining Queued Game Sizes})$$

* **Throughput Tracking**: Parses instantaneous compression and write speeds (`GB/s`, `MB/s`, `KB/s`) reported by the backend.
* **Exponential Moving Average (EMA)**: Applies EMA smoothing (`0.7 \times \text{prior} + 0.3 \times \text{current}`) to prevent ETA jumping due to momentary speed fluctuations.
* **Fallback Throughput**: Measures total queue elapsed time against completed bytes when transitioning between stages before a new speed report arrives.
* **Multi-View Display**: Visible in the queue sidebar, the `OVERALL PROGRESS` card, the header status, and the `Status & Stats` tab.

---

## 🔑 Multi-Password Archive Management

Many archived game dumps (`.zip`, `.rar`, `.7z`) are password-protected. PS5 FFPFSC PRO includes a dedicated **Password Manager**:

* **Priority List**: Store multiple passwords in your settings.
* **Automatic Retry**: If extraction fails with one password, the tool automatically tries the next password in your priority list.
* **No Stalling**: When running batch jobs overnight, password retries happen completely automatically without stopping the queue.

---

---

## 🛠️ Common Issues

### Out of Memory

Try:

* Lowering CPU cores
* Lowering compression level
* Closing other applications

### Disk Full

Ensure sufficient free space exists in both:

* Output folder
* Temporary folder

### Write Errors

Verify that:

* Output locations are valid
* Drives are writable
* Storage devices have enough free space

The application provides detailed error messages and recommended fixes whenever possible.

---

## 🙏 Credits

### Compression Backend

* MkPFS
* Bizkut

### Community

Special thanks to everyone testing games, submitting compatibility reports, reporting bugs, and helping improve the project.

---

## 🔗 Links

📺 YouTube
https://youtube.com/@KINGDKAK

☕ Ko-fi
https://ko-fi.com/KINGDKAK

📥 Releases
https://github.com/KINGDKAK/PS5-FFPFSC-PRO/releases

---

## ⚠️ Disclaimer

This project is provided as-is.

Only use content you legally own and follow all applicable laws in your region.

---

⭐ If you find the project useful, consider starring the repository and contributing compatibility reports to help the community.
