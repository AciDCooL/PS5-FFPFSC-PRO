from __future__ import annotations

import os
import sys
import json
import time
import queue
import socket
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from backend.core import (
    APP_NAME, APP_VERSION, BACKEND_NAME, MKPFS_NAME,
    SETTINGS_FILE, HISTORY_FILE, COMPAT_FILE, COMMUNITY_SHEET_URL,
    load_settings, save_settings, load_history,
    detect_mkpfs_version, upgrade_mkpfs_plugin, revert_mkpfs_plugin,
    QueueEngine,
)

# Global engine singleton for web server
_ENGINE: QueueEngine | None = None


def get_engine() -> QueueEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = QueueEngine()
    return _ENGINE


# ── WebUI HTML / CSS / JS (Single-File Embedded UI) ───────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PS5 FFPFSC PRO — WebUI</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎮</text></svg>">
  <style>
    :root {
      --bg-dark: #0a0a0c;
      --bg-panel: #131317;
      --bg-card: #1c1c24;
      --bg-card2: #242430;
      --border: #2a2a38;
      --border2: #3a3a4e;
      --green: #22c55e;
      --green-dark: #15803d;
      --green-glow: rgba(34, 197, 94, 0.2);
      --red: #ef4444;
      --red-dark: #b91c1c;
      --yellow: #eab308;
      --blue: #3b82f6;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-dark);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: var(--bg-panel);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 20px; font-weight: 800; letter-spacing: 0.5px; color: #fff; }
    .badge {
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-muted);
    }
    .badge-green { border-color: var(--green); color: var(--green); }
    .header-actions { display: flex; align-items: center; gap: 10px; }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid var(--border2);
      background: var(--bg-card);
      color: #fff;
      transition: all 0.15s ease;
      text-decoration: none;
    }
    .btn:hover { background: var(--bg-card2); border-color: #555; }
    .btn-green { background: var(--green); color: #051408; border: none; }
    .btn-green:hover { background: #16a34a; }
    .btn-green:disabled { background: #2f4534; color: #77887b; cursor: not-allowed; }
    .btn-red { background: var(--red); color: #fff; border: none; }
    .btn-red:hover { background: var(--red-dark); }
    .btn-red:disabled { background: #4a2020; color: #886060; cursor: not-allowed; }
    .main-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
      padding: 16px 24px;
      flex: 1;
    }
    @media (max-width: 960px) {
      .main-grid { grid-template-columns: 1fr; }
    }
    .panel {
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .panel-title {
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .input-row { display: flex; gap: 8px; }
    input[type="text"], input[type="password"], select {
      flex: 1;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 12px;
      color: #fff;
      font-size: 13px;
      outline: none;
    }
    input[type="text"]:focus, select:focus { border-color: var(--green); }
    .queue-list {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      min-height: 200px;
      max-height: 340px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
    }
    .queue-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 10px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 12px;
      gap: 8px;
    }
    .queue-item:last-child { border-bottom: none; }
    .queue-item.active { background: rgba(34, 197, 94, 0.12); border-left: 3px solid var(--green); }
    .qi-info { flex: 1; min-width: 0; }
    .qi-title { font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .qi-sub { color: var(--text-muted); font-size: 11px; }
    .qi-actions { display: flex; gap: 4px; }
    .btn-sm { padding: 4px 8px; font-size: 11px; }
    .chip {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .chip-Queued { background: #374151; color: #d1d5db; }
    .chip-Running, .chip-Extracting { background: #166534; color: #86efac; animation: pulse 1.5s infinite; }
    .chip-Done { background: #065f46; color: #6ee7b7; }
    .chip-Failed { background: #991b1b; color: #fca5a5; }
    @keyframes pulse { 0% { opacity: 0.7; } 50% { opacity: 1; } 100% { opacity: 0.7; } }
    .progress-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .p-head { display: flex; justify-content: space-between; align-items: baseline; }
    .p-title { font-size: 12px; font-weight: 700; letter-spacing: 0.5px; color: var(--text-muted); text-transform: uppercase; }
    .p-val { font-size: 24px; font-weight: 800; color: var(--green); }
    .bar-outer {
      background: #111;
      height: 12px;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid #222;
    }
    .bar-inner {
      height: 100%;
      background: linear-gradient(90deg, #15803d, #22c55e);
      width: 0%;
      transition: width 0.3s ease;
    }
    .stages-strip {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 11px;
    }
    .stage-pill { color: var(--text-muted); }
    .stage-pill.active { color: var(--green); font-weight: 700; }
    .stage-pill.done { color: #fff; }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 10px;
    }
    .stat-box {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }
    .stat-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }
    .stat-val { font-size: 14px; font-weight: 700; color: #fff; }
    .tabs-bar { display: flex; gap: 8px; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 8px; }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 4px;
      cursor: pointer;
    }
    .tab-btn.active { background: var(--bg-card2); color: var(--green); }
    .terminal-box {
      background: #070709;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      padding: 10px;
      height: 240px;
      overflow-y: auto;
      white-space: pre-wrap;
      color: #e5e7eb;
      line-height: 1.5;
    }
    .log-line { margin-bottom: 2px; }
    .log-tag { font-weight: bold; border-radius: 3px; padding: 1px 4px; font-size: 10px; margin-right: 6px; }
    .tag-OK { background: #064e3b; color: #6ee7b7; }
    .tag-INFO { background: #1e3a8a; color: #93c5fd; }
    .tag-WARN { background: #78350f; color: #fde047; }
    .tag-ERROR { background: #7f1d1d; color: #fca5a5; }
    .tag-PROGRESS { background: #312e81; color: #c7d2fe; }
    /* Modal styles */
    .modal-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.75);
      display: none; align-items: center; justify-content: center; z-index: 1000;
      backdrop-filter: blur(2px);
    }
    .modal-overlay.open { display: flex; }
    .modal-card {
      background: var(--bg-panel);
      border: 1px solid var(--border2);
      border-radius: 10px;
      width: 90%; max-width: 640px;
      max-height: 85vh;
      display: flex; flex-direction: column;
      box-shadow: 0 20px 40px rgba(0,0,0,0.8);
    }
    .modal-header {
      padding: 16px 20px; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center;
    }
    .modal-header h3 { font-size: 16px; color: #fff; }
    .modal-body { padding: 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 16px; font-size: 13px; }
    .modal-footer { padding: 14px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }
    .fs-list { border: 1px solid var(--border); border-radius: 6px; background: var(--bg-card); max-height: 320px; overflow-y: auto; }
    .fs-item { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
    .fs-item:hover { background: var(--bg-card2); }
    .fs-roots { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    .form-group label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span style="font-size:24px;">🎮</span>
      <div>
        <h1>PS5 FFPFSC PRO</h1>
        <div style="font-size:11px; color:var(--text-muted);">Web & Container Edition &bull; v__APP_VERSION__</div>
      </div>
      <span class="badge badge-green" id="backendBadge">Ready</span>
    </div>
    <div class="header-actions">
      <button class="btn btn-green" id="startBtn" onclick="startQueue()">▶ Start Queue</button>
      <button class="btn btn-red" id="cancelBtn" onclick="cancelQueue()" disabled>✕ Cancel</button>
      <button class="btn" onclick="openSettingsModal()">⚙ Settings</button>
      <a class="btn" href="__COMMUNITY_SHEET_URL__" target="_blank" rel="noopener">🌐 Compat DB</a>
    </div>
  </header>

  <div class="main-grid">

    <!-- Left Column: Queue Manager -->
    <div class="panel">
      <div class="panel-title">
        <span>QUEUE</span>
        <span class="badge" id="queueTotalBadge">0 games</span>
      </div>

      <div class="form-group">
        <label>Add Game / Folder / Archive</label>
        <div class="input-row">
          <input type="text" id="addPathInput" placeholder="/games/PPSA01234 or /path/game.zip">
          <button class="btn btn-sm" onclick="openFsModal()">📁 Browse</button>
        </div>
        <button class="btn btn-green" style="width:100%; justify-content:center; margin-top:4px;" onclick="addPathToQueue()">➕ Scan & Add to Queue</button>
      </div>

      <div class="queue-list" id="queueList">
        <div style="padding:20px; text-align:center; color:var(--text-muted); font-size:12px;">Queue is empty. Browse or type a path above.</div>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
        <span id="batchCounterText" style="color:var(--yellow); font-weight:bold;"></span>
        <button class="btn btn-sm btn-red" onclick="clearQueue()">🗑 Clear Queue</button>
      </div>

      <div id="queueEtaCard" style="display:none; background:var(--bg-card); padding:8px 12px; border-radius:6px; border:1px solid var(--border); font-size:12px; font-weight:bold; color:var(--green);">
        ⏳ Queue ETA: <span id="queueEtaVal">—</span>
      </div>

      <div class="form-group" style="margin-top:auto; padding-top:10px; border-top:1px solid var(--border);">
        <label>Archive Password</label>
        <div class="input-row">
          <input type="password" id="currentPasswordInput" placeholder="Password (if encrypted)">
          <button class="btn btn-sm" onclick="openPasswordsModal()">🔑 List</button>
        </div>
      </div>
    </div>

    <!-- Center/Right Column: Progress & Terminal -->
    <div style="display:flex; flex-direction:column; gap:16px;">

      <!-- Overall Progress Card -->
      <div class="progress-card">
        <div class="p-head">
          <span class="p-title">Overall Progress</span>
          <div style="display:flex; align-items:baseline; gap:12px;">
            <span id="overallEtaLabel" style="font-size:13px; font-weight:700; color:var(--text-muted);"></span>
            <span class="p-val" id="overallPctVal">0%</span>
          </div>
        </div>
        <div class="bar-outer">
          <div class="bar-inner" id="overallBar"></div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
          <span id="stageTitle" style="font-weight:700; font-size:16px; color:#fff;">Ready</span>
          <span id="stagePctVal" style="color:var(--green); font-weight:700; font-size:14px;">0%</span>
        </div>
        <div id="stageDetail" style="font-size:12px; color:var(--text-muted); word-break:break-all;">Queue is idle.</div>
        <div class="bar-outer" style="height:8px;">
          <div class="bar-inner" id="stageBar" style="background:var(--green);"></div>
        </div>
      </div>

      <!-- Stage Breadcrumbs -->
      <div class="stages-strip">
        <span class="stage-pill" id="st_Scan">○ Scan</span>
        <span>›</span>
        <span class="stage-pill" id="st_Read">○ Read</span>
        <span>›</span>
        <span class="stage-pill" id="st_Build">○ Build</span>
        <span>›</span>
        <span class="stage-pill" id="st_Verify">○ Verify</span>
        <span>›</span>
        <span class="stage-pill" id="st_Clean">○ Clean</span>
        <span>›</span>
        <span class="stage-pill" id="st_Done">○ Done</span>
      </div>

      <!-- Real-Time Stats -->
      <div class="stats-grid">
        <div class="stat-box">
          <div class="stat-label">Speed</div>
          <div class="stat-val" id="statSpeed">—</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Elapsed</div>
          <div class="stat-val" id="statElapsed">00:00</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Game ETA</div>
          <div class="stat-val" id="statGameEta">—</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Queue ETA</div>
          <div class="stat-val" id="statQueueEta">—</div>
        </div>
      </div>

      <!-- Tabbed Logs & History -->
      <div class="panel" style="flex:1;">
        <div class="tabs-bar">
          <button class="tab-btn active" onclick="switchTab('logs', this)">Live Logs</button>
          <button class="tab-btn" onclick="switchTab('history', this)">Recent History</button>
          <div style="margin-left:auto; display:flex; gap:6px;">
            <button class="btn btn-sm" onclick="clearLogs()">Clear</button>
            <button class="btn btn-sm" onclick="copyLogs()">Copy</button>
          </div>
        </div>

        <div id="tabLogs" class="terminal-box"></div>
        <div id="tabHistory" style="display:none; max-height:240px; overflow-y:auto;">
          <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:left;">
            <thead>
              <tr style="border-bottom:1px solid var(--border); color:var(--text-muted);">
                <th style="padding:6px;">Date</th>
                <th style="padding:6px;">Title ID</th>
                <th style="padding:6px;">Name</th>
                <th style="padding:6px;">Original</th>
                <th style="padding:6px;">Output</th>
              </tr>
            </thead>
            <tbody id="historyBody"></tbody>
          </table>
        </div>
      </div>

    </div>
  </div>

  <!-- In-Browser File/Folder Browser Modal -->
  <div class="modal-overlay" id="fsModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3>Server File & Folder Browser</h3>
        <button class="btn btn-sm" onclick="closeFsModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="fs-roots" id="fsRoots"></div>
        <div style="display:flex; gap:8px;">
          <input type="text" id="fsCurrentPath" readonly style="background:#111;">
          <button class="btn btn-sm" id="fsUpBtn" onclick="browseFsParent()">↑ Up</button>
        </div>
        <div class="fs-list" id="fsEntriesList"></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-green" onclick="selectCurrentFsFolder()">Select This Folder</button>
        <button class="btn" onclick="closeFsModal()">Cancel</button>
      </div>
    </div>
  </div>

  <!-- Settings Modal -->
  <div class="modal-overlay" id="settingsModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3>Options & Settings</h3>
        <button class="btn btn-sm" onclick="closeSettingsModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label>Default Output Folder</label>
          <input type="text" id="set_output_folder" placeholder="/output or D:\\Output">
        </div>
        <div class="form-group">
          <label>Default Temp Folder</label>
          <input type="text" id="set_temp_folder" placeholder="/temp or D:\\Temp">
        </div>
        <div class="form-group">
          <label>AMPR Emu Folder (Optional)</label>
          <input type="text" id="set_ampr_folder" placeholder="/ampr_emu">
        </div>
        <div class="form-group">
          <label>Output Naming Format</label>
          <select id="set_naming_format">
            <option value="Title ID">Title ID (e.g. PPSA01234.ffpfsc)</option>
            <option value="Game Name">Game Name (e.g. Astro_Playroom.ffpfsc)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Compression Level (0 = Store, 9 = Maximum)</label>
          <input type="range" id="set_compression_level" min="0" max="9" step="1" oninput="document.getElementById('compVal').innerText = this.value">
          <span id="compVal" style="color:var(--green); font-weight:bold;">9</span>
        </div>
        <div class="form-group">
          <label>CPU Cores (0 = Auto)</label>
          <input type="number" id="set_cpu_count" min="0" max="64" value="0">
        </div>
        <div class="form-group">
          <label>Block Size</label>
          <select id="set_block_size">
            <option value="auto">auto (65536)</option>
            <option value="auto-fit">auto-fit (minimise waste)</option>
            <option value="65536">65536</option>
            <option value="32768">32768</option>
            <option value="16384">16384</option>
          </select>
        </div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          <label><input type="checkbox" id="set_keep_pfs"> Keep intermediate PFS image</label>
          <label><input type="checkbox" id="set_verify_output"> Verify output image</label>
          <label><input type="checkbox" id="set_auto_clear_temp"> Auto-clear temp folder after success</label>
          <label><input type="checkbox" id="set_disable_ampr_prompt"> Disable APR/AMPR question</label>
          <label><input type="checkbox" id="set_per_game_folder"> Create per-game output subfolder</label>
          <label><input type="checkbox" id="set_verbose"> Verbose mkpfs debug output</label>
          <label><input type="checkbox" id="set_offline_mode"> Strict offline mode</label>
        </div>
        <div style="border-top:1px solid var(--border); padding-top:12px;">
          <div style="font-weight:bold; margin-bottom:6px;">MkPFS Engine</div>
          <div id="mkpfsStatusText" style="color:var(--text-muted); font-size:12px; margin-bottom:4px;">Checking...</div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-green" onclick="saveSettingsModal()">Save Changes</button>
        <button class="btn" onclick="closeSettingsModal()">Close</button>
      </div>
    </div>
  </div>

  <!-- Passwords Modal -->
  <div class="modal-overlay" id="passwordsModal">
    <div class="modal-card" style="max-width:440px;">
      <div class="modal-header">
        <h3>Archive Passwords Manager</h3>
        <button class="btn btn-sm" onclick="closePasswordsModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="input-row">
          <input type="text" id="newPasswordInput" placeholder="Enter archive password">
          <button class="btn btn-sm btn-green" onclick="addPassword()">Add</button>
        </div>
        <div id="passwordsList" style="border:1px solid var(--border); border-radius:6px; background:var(--bg-card); max-height:200px; overflow-y:auto;"></div>
      </div>
      <div class="modal-footer">
        <button class="btn" onclick="closePasswordsModal()">Close</button>
      </div>
    </div>
  </div>

  <script>
    let sseSource = null;
    let autoScrollLogs = true;

    async function init() {
      setupSSE();
      loadQueue();
      loadStatus();
      loadHistory();
      // Polling fallback
      setInterval(loadStatus, 1000);
    }

    function setupSSE() {
      if (window.EventSource) {
        sseSource = new EventSource('/api/events');
        sseSource.onmessage = function(e) {
          try {
            const ev = JSON.parse(e.data);
            if (ev.type === 'status') {
              renderStatus(ev.data);
            } else if (ev.type === 'queue') {
              renderQueue(ev.data);
            } else if (ev.type === 'log') {
              appendLogLine(ev.data);
            }
          } catch(err) {}
        };
      }
    }

    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        renderStatus(data);
      } catch (err) {}
    }

    function renderStatus(st) {
      document.getElementById('startBtn').disabled = st.is_running;
      document.getElementById('cancelBtn').disabled = !st.is_running;
      document.getElementById('overallPctVal').innerText = st.overall_pct + '%';
      document.getElementById('overallBar').style.width = st.overall_pct + '%';
      document.getElementById('stageTitle').innerText = st.stage || 'Ready';
      document.getElementById('stagePctVal').innerText = st.stage_pct + '%';
      document.getElementById('stageBar').style.width = st.stage_pct + '%';
      document.getElementById('stageDetail').innerText = st.detail || '';
      document.getElementById('statSpeed').innerText = st.speed || '—';
      document.getElementById('statElapsed').innerText = st.elapsed || '00:00';
      document.getElementById('statGameEta').innerText = st.game_eta || '—';
      document.getElementById('statQueueEta').innerText = st.queue_eta || '—';

      if (st.is_running && st.queue_eta && st.queue_eta !== '—') {
        document.getElementById('queueEtaCard').style.display = 'block';
        document.getElementById('queueEtaVal').innerText = st.queue_eta;
        document.getElementById('overallEtaLabel').innerText = 'Queue ETA: ' + st.queue_eta;
      } else {
        document.getElementById('queueEtaCard').style.display = 'none';
        document.getElementById('overallEtaLabel').innerText = '';
      }

      if (st.is_running && st.batch_total > 0) {
        document.getElementById('batchCounterText').innerText =
          'Game ' + st.current_index + '/' + st.batch_total + '  |  ✓ ' + st.batch_done + '  ✗ ' + st.batch_failed;
      } else {
        document.getElementById('batchCounterText').innerText = '';
      }

      // Stage pills
      ['Scan', 'Read', 'Build', 'Verify', 'Clean', 'Done'].forEach(s => {
        const el = document.getElementById('st_' + s);
        if (el) {
          el.className = 'stage-pill';
          if (st.stage && st.stage.toLowerCase().includes(s.toLowerCase())) {
            el.className = 'stage-pill active';
          }
        }
      });
    }

    async function loadQueue() {
      try {
        const res = await fetch('/api/queue');
        const q = await res.json();
        renderQueue(q);
      } catch (err) {}
    }

    function renderQueue(items) {
      const el = document.getElementById('queueList');
      document.getElementById('queueTotalBadge').innerText = items.length + ' game' + (items.length !== 1 ? 's' : '');
      if (!items || items.length === 0) {
        el.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:12px;">Queue is empty. Browse or type a path above.</div>';
        return;
      }
      el.innerHTML = items.map((it, idx) => `
        <div class="queue-item ${it.status === 'Running' || it.status === 'Extracting' ? 'active' : ''}">
          <div class="qi-info">
            <div class="qi-title">${it.name}</div>
            <div class="qi-sub">${it.title_id} &bull; ${it.formatted_size}</div>
          </div>
          <span class="chip chip-${it.status}">${it.status}</span>
          <div class="qi-actions">
            <button class="btn btn-sm" onclick="moveQueueItem(${idx}, ${idx - 1})">↑</button>
            <button class="btn btn-sm" onclick="moveQueueItem(${idx}, ${idx + 1})">↓</button>
            <button class="btn btn-sm btn-red" onclick="removeQueueItem(${idx})">✕</button>
          </div>
        </div>
      `).join('');
    }

    async function addPathToQueue() {
      const inp = document.getElementById('addPathInput');
      const val = inp.value.trim();
      if (!val) return alert('Enter or browse a file or folder path.');
      const res = await fetch('/api/queue/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: val})
      });
      const data = await res.json();
      if (data.added && data.added.length > 0) {
        inp.value = '';
        loadQueue();
      } else {
        alert(data.error || 'No compatible games, archives, or images found at that path.');
      }
    }

    async function removeQueueItem(idx) {
      await fetch('/api/queue/remove', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({index: idx})
      });
      loadQueue();
    }

    async function moveQueueItem(from, to) {
      if (to < 0) return;
      await fetch('/api/queue/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from: from, to: to})
      });
      loadQueue();
    }

    async function clearQueue() {
      if (!confirm('Clear all queued games?')) return;
      await fetch('/api/queue/clear', {method: 'POST'});
      loadQueue();
    }

    async function startQueue() {
      const res = await fetch('/api/queue/start', {method: 'POST'});
      const data = await res.json();
      if (!data.ok) alert(data.error);
      loadStatus();
    }

    async function cancelQueue() {
      if (!confirm('Cancel queue processing?')) return;
      await fetch('/api/queue/cancel', {method: 'POST'});
      loadStatus();
    }

    function appendLogLine(entry) {
      const box = document.getElementById('tabLogs');
      const div = document.createElement('div');
      div.className = 'log-line';
      div.innerHTML = `<span style="color:#666;">[${entry.timestamp}]</span> <span class="log-tag tag-${entry.tag}">${entry.tag}</span> ${escapeHtml(entry.message)}`;
      box.appendChild(div);
      if (autoScrollLogs) {
        box.scrollTop = box.scrollHeight;
      }
    }

    function clearLogs() {
      document.getElementById('tabLogs').innerHTML = '';
    }

    function copyLogs() {
      const text = document.getElementById('tabLogs').innerText;
      navigator.clipboard.writeText(text);
      alert('Logs copied to clipboard!');
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function switchTab(tab, btn) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tabLogs').style.display = tab === 'logs' ? 'block' : 'none';
      document.getElementById('tabHistory').style.display = tab === 'history' ? 'block' : 'none';
      if (tab === 'history') loadHistory();
    }

    async function loadHistory() {
      const res = await fetch('/api/history');
      const data = await res.json();
      const tbody = document.getElementById('historyBody');
      if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="padding:10px; text-align:center; color:#666;">No compressions recorded yet.</td></tr>';
        return;
      }
      tbody.innerHTML = data.map(h => `
        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
          <td style="padding:6px; color:#888;">${h.date || '—'}</td>
          <td style="padding:6px; font-weight:bold; color:var(--green);">${h.title_id || '—'}</td>
          <td style="padding:6px;">${h.name || '—'}</td>
          <td style="padding:6px; color:#aaa;">${h.orig_size ? (h.orig_size / (1024*1024*1024)).toFixed(2) + ' GB' : '—'}</td>
          <td style="padding:6px; color:#aaa;">${h.final_size ? (h.final_size / (1024*1024*1024)).toFixed(2) + ' GB' : '—'}</td>
        </tr>
      `).join('');
    }

    // Server File Browser
    let currentBrowsePath = '';
    async function openFsModal() {
      document.getElementById('fsModal').classList.add('open');
      browseFs('');
    }
    function closeFsModal() {
      document.getElementById('fsModal').classList.remove('open');
    }
    async function browseFs(path) {
      const res = await fetch('/api/fs/browse?path=' + encodeURIComponent(path));
      const data = await res.json();
      currentBrowsePath = data.current;
      document.getElementById('fsCurrentPath').value = data.current;
      document.getElementById('fsUpBtn').disabled = !data.parent;
      document.getElementById('fsUpBtn').onclick = () => browseFs(data.parent);

      // Roots
      const rBox = document.getElementById('fsRoots');
      rBox.innerHTML = (data.roots || []).map(r => `
        <button class="btn btn-sm" onclick="browseFs('${escapeJs(r.path)}')">${r.name}</button>
      `).join('');

      // Entries
      const list = document.getElementById('fsEntriesList');
      if (!data.entries || data.entries.length === 0) {
        list.innerHTML = '<div style="padding:12px; color:#888;">(Empty directory)</div>';
        return;
      }
      list.innerHTML = data.entries.map(e => `
        <div class="fs-item" onclick="${e.is_dir ? `browseFs('${escapeJs(e.path)}')` : `selectFsFile('${escapeJs(e.path)}')`}">
          <span>${e.is_dir ? '📁' : '📄'} ${e.name}</span>
          <span style="font-size:11px; color:#888;">${e.size}</span>
        </div>
      `).join('');
    }
    function browseFsParent() {
      // Handled dynamically by Up button
    }
    function selectCurrentFsFolder() {
      document.getElementById('addPathInput').value = currentBrowsePath;
      closeFsModal();
    }
    function selectFsFile(filePath) {
      document.getElementById('addPathInput').value = filePath;
      closeFsModal();
    }
    function escapeJs(str) {
      return (str || '').replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
    }

    // Settings Modal
    async function openSettingsModal() {
      document.getElementById('settingsModal').classList.add('open');
      const res = await fetch('/api/settings');
      const s = await res.json();
      document.getElementById('set_output_folder').value = s.output_folder || '';
      document.getElementById('set_temp_folder').value = s.temp_folder || '';
      document.getElementById('set_ampr_folder').value = s.ampr_folder || '';
      document.getElementById('set_naming_format').value = s.naming_format || 'Title ID';
      document.getElementById('set_compression_level').value = s.compression_level ?? 9;
      document.getElementById('compVal').innerText = s.compression_level ?? 9;
      document.getElementById('set_cpu_count').value = s.cpu_count ?? 0;
      document.getElementById('set_block_size').value = s.block_size || 'auto';
      document.getElementById('set_keep_pfs').checked = !!s.keep_pfs;
      document.getElementById('set_verify_output').checked = !!s.verify_output;
      document.getElementById('set_auto_clear_temp').checked = !!s.auto_clear_temp;
      document.getElementById('set_disable_ampr_prompt').checked = (s.disable_ampr_prompt !== undefined) ? !!s.disable_ampr_prompt : true;
      document.getElementById('set_per_game_folder').checked = !!s.per_game_folder;
      document.getElementById('set_verbose').checked = !!s.verbose;
      document.getElementById('set_offline_mode').checked = !!s.offline_mode;

      // Plugins info
      const pRes = await fetch('/api/plugins');
      const pData = await pRes.json();
      document.getElementById('mkpfsStatusText').innerText = 'Active: v' + pData.version + ' [' + pData.source + ']';
    }
    function closeSettingsModal() {
      document.getElementById('settingsModal').classList.remove('open');
    }
    async function saveSettingsModal() {
      const payload = {
        output_folder: document.getElementById('set_output_folder').value.trim(),
        temp_folder: document.getElementById('set_temp_folder').value.trim(),
        ampr_folder: document.getElementById('set_ampr_folder').value.trim(),
        naming_format: document.getElementById('set_naming_format').value,
        compression_level: parseInt(document.getElementById('set_compression_level').value, 10),
        cpu_count: parseInt(document.getElementById('set_cpu_count').value, 10),
        block_size: document.getElementById('set_block_size').value,
        keep_pfs: document.getElementById('set_keep_pfs').checked,
        verify_output: document.getElementById('set_verify_output').checked,
        auto_clear_temp: document.getElementById('set_auto_clear_temp').checked,
        disable_ampr_prompt: document.getElementById('set_disable_ampr_prompt').checked,
        per_game_folder: document.getElementById('set_per_game_folder').checked,
        verbose: document.getElementById('set_verbose').checked,
        offline_mode: document.getElementById('set_offline_mode').checked,
      };
      await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      closeSettingsModal();
    }

    // Passwords Manager Modal
    async function openPasswordsModal() {
      document.getElementById('passwordsModal').classList.add('open');
      loadPasswords();
    }
    function closePasswordsModal() {
      document.getElementById('passwordsModal').classList.remove('open');
    }
    async function loadPasswords() {
      const res = await fetch('/api/passwords');
      const pwds = await res.json();
      const list = document.getElementById('passwordsList');
      if (!pwds || pwds.length === 0) {
        list.innerHTML = '<div style="padding:10px; color:#888; font-size:12px;">No saved passwords.</div>';
        return;
      }
      list.innerHTML = pwds.map((p, idx) => `
        <div class="fs-item">
          <span>${idx + 1}. ${escapeHtml(p)}</span>
          <button class="btn btn-sm btn-red" onclick="removePassword(${idx})">✕</button>
        </div>
      `).join('');
    }
    async function addPassword() {
      const inp = document.getElementById('newPasswordInput');
      const val = inp.value.trim();
      if (!val) return;
      const res = await fetch('/api/passwords', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'add', password: val})
      });
      inp.value = '';
      loadPasswords();
    }
    async function removePassword(idx) {
      await fetch('/api/passwords', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'remove', index: idx})
      });
      loadPasswords();
    }

    window.onload = init;
  </script>
</body>
</html>
"""


# ── HTTP Request Handler ──────────────────────────────────────────────────────

class WebHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Silence verbose standard server request logs to keep terminal clean
        pass

    def _send_json(self, data: dict | list, status: int = 200):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        query = urllib.parse.parse_qs(url.query)
        engine = get_engine()

        # ── Root / HTML Page ───────────────────────────────────────────────────
        if path in ("/", "/index.html"):
            rendered = (HTML_TEMPLATE
                        .replace("__APP_VERSION__", APP_VERSION)
                        .replace("__COMMUNITY_SHEET_URL__", COMMUNITY_SHEET_URL))
            body = rendered.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ── Server-Sent Events (SSE) Stream ───────────────────────────────────
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            ev_q = engine.subscribe_events()
            try:
                # Send initial state
                init_msg = json.dumps({"type": "status", "data": engine.get_state()})
                self.wfile.write(f"data: {init_msg}\n\n".encode("utf-8"))
                self.wfile.flush()

                while True:
                    try:
                        ev = ev_q.get(timeout=15.0)
                        msg = json.dumps(ev, ensure_ascii=False)
                        self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Keep-alive ping
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                engine.unsubscribe_events(ev_q)
            return

        # ── REST Endpoints ────────────────────────────────────────────────────
        if path == "/api/status":
            self._send_json(engine.get_state())
            return

        if path == "/api/queue":
            self._send_json(engine.get_queue())
            return

        if path == "/api/settings":
            self._send_json(load_settings())
            return

        if path == "/api/passwords":
            s = load_settings()
            self._send_json(s.get("archive_passwords", []))
            return

        if path == "/api/logs":
            self._send_json(engine.get_logs())
            return

        if path == "/api/history":
            self._send_json(load_history())
            return

        if path == "/api/plugins":
            v, src = detect_mkpfs_version()
            self._send_json({"version": v, "source": src})
            return

        if path == "/api/fs/browse":
            target = query.get("path", [""])[0]
            self._send_json(engine.browse_filesystem(target))
            return

        self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        engine = get_engine()

        if path == "/api/queue/add":
            body = self._read_json()
            target_path = body.get("path", "")
            added = engine.add_path(target_path)
            if added:
                self._send_json({"ok": True, "added": added})
            else:
                self._send_json({"ok": False, "error": f"No compatible PS5 games, archives, or images found at: {target_path}"}, status=400)
            return

        if path == "/api/queue/remove":
            body = self._read_json()
            idx = int(body.get("index", -1))
            ok = engine.remove_at(idx)
            self._send_json({"ok": ok})
            return

        if path == "/api/queue/move":
            body = self._read_json()
            from_idx = int(body.get("from", -1))
            to_idx = int(body.get("to", -1))
            ok = engine.move_item(from_idx, to_idx)
            self._send_json({"ok": ok})
            return

        if path == "/api/queue/clear":
            ok = engine.clear_queue()
            self._send_json({"ok": ok})
            return

        if path == "/api/queue/start":
            ok, msg = engine.start_queue()
            self._send_json({"ok": ok, "message": msg, "error": None if ok else msg}, status=200 if ok else 400)
            return

        if path == "/api/queue/cancel":
            ok, msg = engine.cancel_queue()
            self._send_json({"ok": ok, "message": msg})
            return

        if path == "/api/settings":
            body = self._read_json()
            save_settings(body)
            self._send_json({"ok": True, "settings": load_settings()})
            return

        if path == "/api/passwords":
            body = self._read_json()
            action = body.get("action", "add")
            s = load_settings()
            pwds = list(s.get("archive_passwords", []))
            if action == "add":
                pwd = body.get("password", "").strip()
                if pwd and pwd not in pwds:
                    pwds.append(pwd)
            elif action == "remove":
                idx = int(body.get("index", -1))
                if 0 <= idx < len(pwds):
                    pwds.pop(idx)
            save_settings({"archive_passwords": pwds})
            self._send_json({"ok": True, "passwords": pwds})
            return

        if path == "/api/plugins/upgrade":
            ok, msg = upgrade_mkpfs_plugin()
            self._send_json({"ok": ok, "message": msg})
            return

        if path == "/api/plugins/revert":
            ok = revert_mkpfs_plugin()
            self._send_json({"ok": ok, "message": "Reverted MkPFS to bundled version."})
            return

        self._send_json({"error": "Not Found"}, status=404)


# ── Server Runner ─────────────────────────────────────────────────────────────

def run_web_server(host: str = "0.0.0.0", port: int = 8080, engine: QueueEngine | None = None):
    """Run the headless web server."""
    global _ENGINE
    if engine is not None:
        _ENGINE = engine
    else:
        _ENGINE = get_engine()

    server_address = (host, port)
    try:
        httpd = ThreadingHTTPServer(server_address, WebHandler)
    except OSError as e:
        print(f"[ERROR] Could not bind to {host}:{port}: {e}")
        return

    banner = f"""
======================================================================
  {APP_NAME} v{APP_VERSION} — Web & Container Interface
======================================================================
  Listening on:   http://{host}:{port}
  Local access:   http://localhost:{port}
  MkPFS active:   v{detect_mkpfs_version()[0]} [{detect_mkpfs_version()[1]}]
======================================================================
"""
    print(banner)
    _ENGINE.log("INFO", f"WebUI server started on http://{host}:{port}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down WebUI server...")
    finally:
        httpd.server_close()
        print("[INFO] Server stopped.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host binding (default: 0.0.0.0)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port binding (default: 8080)")
    args = parser.parse_args()
    run_web_server(host=args.host, port=args.port)
