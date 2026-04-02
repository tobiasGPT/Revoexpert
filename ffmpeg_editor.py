from flask import Flask, request, jsonify, render_template_string, send_file
import subprocess, os, glob, json, uuid

app = Flask(__name__)

def env_path(name, default):
    return os.path.expanduser(os.getenv(name, default))

def env_int(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

def trim_srt_segment(srt_path, start_s, end_s, out_path):
    """Trim an SRT file to [start_s, end_s] and write shifted timestamps."""
    def ts_to_s(ts):
        ts = ts.strip().split()[0]  # strip VTT positioning
        h, m, s = ts.replace(',', '.').split(':')
        return int(h)*3600 + int(m)*60 + float(s)

    def s_to_ts(sec):
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.', ',')

    try:
        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
    except Exception:
        return False

    blocks = re.split(r'\n\s*\n', raw.strip())
    entries = []
    for block in blocks:
        lines = [l.rstrip() for l in block.strip().split('\n') if l.strip()]
        ts_line = next((l for l in lines if '-->' in l), None)
        if not ts_line:
            continue
        parts = ts_line.split('-->')
        if len(parts) != 2:
            continue
        try:
            t0 = ts_to_s(parts[0])
            t1 = ts_to_s(parts[1])
        except Exception:
            continue
        if t1 <= start_s or t0 >= end_s:
            continue
        text_lines = [l for l in lines if l != ts_line and not l.strip().isdigit()]
        text = re.sub(r'<[^>]+>', '', '\n'.join(text_lines)).strip()
        if not text:
            continue
        entries.append((max(0, t0 - start_s), min(end_s - start_s, t1 - start_s), text))

    if not entries:
        return False

    out_blocks = []
    for idx, (t0, t1, text) in enumerate(entries, 1):
        out_blocks.append(f"{idx}\n{s_to_ts(t0)} --> {s_to_ts(t1)}\n{text}")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(out_blocks) + '\n')
    return True

CAPCUT_DIR = env_path("REVO_CAPCUT_DIR", "/Users/tobiaslundgren/Movies/CapCut")
EDITED_DIR = env_path("REVO_EDITED_DIR", os.path.join(CAPCUT_DIR, "vivi_edited"))
REELS_DIR = env_path("REVO_REELS_DIR", os.path.join(CAPCUT_DIR, "reels"))
OVERLAY = env_path("REVO_OVERLAY_PATH", os.path.join(CAPCUT_DIR, "viviandco_overlay.png"))
FFMPEG = env_path("REVO_FFMPEG_BIN", "/opt/homebrew/Cellar/ffmpeg-full/8.1/bin/ffmpeg")
FFPROBE = env_path("REVO_FFPROBE_BIN", "/opt/homebrew/bin/ffprobe")
YTDLP = env_path("REVO_YTDLP_BIN", "/opt/homebrew/bin/yt-dlp")
PORT = env_int("REVO_PORT", 7777)

VIDEO_PATTERNS = ("*.mov", "*.mp4", "*.MOV", "*.MP4")
ALLOWED_MEDIA_ROOTS = (CAPCUT_DIR, EDITED_DIR, REELS_DIR)

os.makedirs(EDITED_DIR, exist_ok=True)
os.makedirs(REELS_DIR, exist_ok=True)

def iter_video_paths(directory):
    for pattern in VIDEO_PATTERNS:
        yield from glob.glob(os.path.join(directory, pattern))

def describe_video(path):
    size = os.path.getsize(path)
    return {
        "name": os.path.basename(path),
        "path": path,
        "size": f"{size/1024/1024:.1f}MB",
        "mtime": int(os.path.getmtime(path)),
    }

def list_videos(directory):
    files = [describe_video(path) for path in iter_video_paths(directory) if os.path.isfile(path)]
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files

def resolve_media_path(raw_path):
    if not raw_path:
        return None
    candidate = os.path.realpath(raw_path)
    if not os.path.isfile(candidate):
        return None
    if os.path.splitext(candidate)[1].lower() not in {".mov", ".mp4"}:
        return None
    for root in ALLOWED_MEDIA_ROOTS:
        root_path = os.path.realpath(root)
        if candidate == root_path or candidate.startswith(root_path + os.sep):
            return candidate
    return None

def get_tool_status():
    return {
        "ffmpeg": os.path.exists(FFMPEG),
        "ffprobe": os.path.exists(FFPROBE),
        "yt_dlp": os.path.exists(YTDLP),
        "overlay": os.path.exists(OVERLAY),
    }

def get_tool_versions():
    commands = {
        "ffmpeg": [FFMPEG, "-version"],
        "ffprobe": [FFPROBE, "-version"],
        "yt_dlp": [YTDLP, "--version"],
    }
    versions = {}
    for key, command in commands.items():
        if not os.path.exists(command[0]):
            versions[key] = None
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            first_line = (result.stdout or result.stderr or "").strip().splitlines()
            versions[key] = first_line[0] if first_line else None
        except Exception:
            versions[key] = None
    return versions

def get_workspace_snapshot():
    tools = get_tool_status()
    source_files = list_videos(CAPCUT_DIR)
    edited_files = list_videos(EDITED_DIR)
    reel_files = list_videos(REELS_DIR)
    return {
        "tools": tools,
        "counts": {
            "source": len(source_files),
            "edited": len(edited_files),
            "reels": len(reel_files),
        },
        "directories": {
            "source": CAPCUT_DIR,
            "edited": EDITED_DIR,
            "reels": REELS_DIR,
        },
        "config": {
            "overlay": OVERLAY,
            "port": PORT,
        },
        "tool_versions": get_tool_versions(),
        "recent_outputs": {
            "edited": edited_files[:8],
            "reels": reel_files[:8],
        },
        "ready": all(tools.values()),
    }

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEXUS // Video Editor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;800&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  :root {
    --bg:#0a0a0f; --panel:#111118; --accent:#00f0ff; --accent-dim:#00f0ff20;
    --alert:#ff2a6d; --success:#00ff88; --text:#e0e0e8; --text-dim:#606070;
  }
  body { font-family:'JetBrains Mono',monospace; background:var(--bg); color:var(--text); min-height:100vh; padding:2rem; }
  .grid-bg { position:fixed; top:0; left:0; width:100%; height:100%; background-image:linear-gradient(rgba(0,240,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,240,255,0.03) 1px,transparent 1px); background-size:50px 50px; pointer-events:none; z-index:0; }
  .grid-bg::before { content:''; position:absolute; inset:0; background:radial-gradient(ellipse at center,transparent 0%,var(--bg) 100%); }
  header { position:relative; z-index:10; padding-bottom:1.5rem; border-bottom:1px solid rgba(0,240,255,0.1); display:flex; justify-content:space-between; align-items:center; margin-bottom:2rem; }
  .logo { font-size:1.5rem; font-weight:800; letter-spacing:0.2em; position:relative; }
  .logo::after { content:'NEXUS'; position:absolute; left:2px; top:2px; color:var(--accent); opacity:0.3; }
  .subtitle { font-size:0.75rem; color:var(--text-dim); letter-spacing:0.1em; }
  .header-meta { display:flex; flex-direction:column; align-items:flex-end; gap:0.75rem; }
  .chip-btn { display:inline-flex; align-items:center; justify-content:center; gap:0.45rem; padding:0.55rem 0.9rem; border-radius:999px; border:1px solid rgba(0,240,255,0.18); background:rgba(0,240,255,0.06); color:var(--accent); font-family:inherit; font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; cursor:pointer; transition:all 0.2s; }
  .chip-btn:hover { background:rgba(0,240,255,0.12); border-color:rgba(0,240,255,0.3); }
  .chip-btn.small { padding:0.45rem 0.75rem; font-size:0.68rem; }
  .status-grid { position:relative; z-index:10; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; max-width:1400px; margin:0 auto 1.5rem; }
  .status-card { background:linear-gradient(180deg, rgba(17,17,24,0.92), rgba(8,8,12,0.92)); border:1px solid rgba(0,240,255,0.1); border-radius:10px; padding:1rem 1.1rem; box-shadow:0 18px 45px rgba(0,0,0,0.18); }
  .status-head { display:flex; align-items:center; justify-content:space-between; gap:0.75rem; margin-bottom:0.6rem; }
  .status-label { font-size:0.68rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--text-dim); }
  .status-value { font-size:1.75rem; font-weight:800; letter-spacing:-0.04em; }
  .status-note { font-size:0.72rem; color:var(--text-dim); line-height:1.5; word-break:break-word; }
  .status-pill { display:inline-flex; align-items:center; gap:0.35rem; border-radius:999px; padding:0.25rem 0.55rem; font-size:0.62rem; letter-spacing:0.12em; text-transform:uppercase; border:1px solid rgba(255,255,255,0.08); }
  .status-pill.ok { color:var(--success); border-color:rgba(0,255,136,0.18); background:rgba(0,255,136,0.08); }
  .status-pill.warn { color:#ffcf6e; border-color:rgba(255,207,110,0.18); background:rgba(255,207,110,0.08); }
  .status-pill.danger { color:var(--alert); border-color:rgba(255,42,109,0.18); background:rgba(255,42,109,0.08); }

  /* Tabs */
  .tabs { position:relative; z-index:10; display:flex; gap:0; margin-bottom:2rem; border-bottom:1px solid rgba(0,240,255,0.1); }
  .tab { padding:0.75rem 2rem; font-size:0.75rem; letter-spacing:0.15em; text-transform:uppercase; cursor:pointer; border:1px solid transparent; border-bottom:none; margin-bottom:-1px; color:var(--text-dim); transition:all 0.2s; }
  .tab:hover { color:var(--text); }
  .tab.active { color:var(--accent); border-color:rgba(0,240,255,0.2); background:var(--panel); border-bottom-color:var(--panel); }
  .tab-content { display:none; }
  .tab-content.active { display:block; }

  .layout { position:relative; z-index:10; display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; max-width:1400px; margin:0 auto; }
  .layout-3 { position:relative; z-index:10; display:grid; grid-template-columns:1fr 1fr 1fr; gap:1.5rem; max-width:1400px; margin:0 auto; }
  .col { display:flex; flex-direction:column; gap:1.5rem; }
  .card { background:var(--panel); border:1px solid rgba(0,240,255,0.1); border-radius:8px; padding:1.5rem; }
  .card-title { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--text-dim); margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid rgba(0,240,255,0.08); }
  .card-title-row { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid rgba(0,240,255,0.08); }
  .card-title-row .card-title { margin:0; padding:0; border:0; }
  label { font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:0.4rem; margin-top:1rem; }
  label:first-of-type { margin-top:0; }
  input[type=text], input[type=url], input[type=number], select {
    width:100%; background:#0a0a12; border:1px solid rgba(0,240,255,0.15); color:var(--text);
    padding:0.6rem 0.75rem; border-radius:4px; font-family:inherit; font-size:0.8rem; outline:none;
  }
  input:focus, select:focus { border-color:var(--accent); }
  input[type=range] { width:100%; background:transparent; border:none; padding:0.3rem 0; cursor:pointer; accent-color:var(--accent); outline:none; }
  .range-row { display:flex; align-items:center; gap:0.75rem; }
  .range-val { font-size:0.8rem; color:var(--accent); min-width:40px; text-align:right; }
  .toggle-row { display:flex; align-items:center; gap:0.75rem; margin-top:1rem; }
  .toggle { position:relative; width:40px; height:22px; flex-shrink:0; }
  .toggle input { opacity:0; width:0; height:0; }
  .slider-toggle { position:absolute; inset:0; background:#1a1a2e; border-radius:22px; cursor:pointer; transition:0.3s; border:1px solid rgba(0,240,255,0.2); }
  .slider-toggle::before { content:''; position:absolute; height:16px; width:16px; left:2px; bottom:2px; background:var(--text-dim); border-radius:50%; transition:0.3s; }
  input:checked + .slider-toggle { background:rgba(0,240,255,0.15); border-color:var(--accent); }
  input:checked + .slider-toggle::before { transform:translateX(18px); background:var(--accent); }
  .toggle-label { font-size:0.78rem; color:var(--text-dim); }
  .btn { width:100%; padding:0.85rem; margin-top:1rem; background:transparent; border:1px solid var(--accent); color:var(--accent); border-radius:6px; font-family:inherit; font-size:0.8rem; letter-spacing:0.15em; text-transform:uppercase; cursor:pointer; transition:all 0.2s; }
  .btn:hover { background:rgba(0,240,255,0.08); box-shadow:0 0 20px rgba(0,240,255,0.15); }
  .btn:disabled { opacity:0.4; cursor:not-allowed; }
  .btn.danger { border-color:var(--alert); color:var(--alert); }
  .btn.danger:hover { background:rgba(255,42,109,0.08); }
  .btn.success-btn { border-color:var(--success); color:var(--success); }
  .file-list { max-height:280px; overflow-y:auto; }
  .file-item { padding:0.6rem 0.75rem; border-radius:4px; cursor:pointer; font-size:0.78rem; border:1px solid transparent; margin-bottom:0.3rem; transition:all 0.2s; display:flex; justify-content:space-between; align-items:center; }
  .file-item:hover { background:var(--accent-dim); border-color:rgba(0,240,255,0.2); }
  .file-item.selected { background:rgba(0,240,255,0.12); border-color:var(--accent); color:var(--accent); }
  .file-size { font-size:0.7rem; color:var(--text-dim); }
  .recent-list { display:flex; flex-direction:column; gap:0.5rem; margin-top:1rem; }
  .recent-item { display:flex; align-items:center; justify-content:space-between; gap:0.75rem; padding:0.7rem 0.85rem; border-radius:6px; background:#0a0a12; border:1px solid rgba(0,240,255,0.08); font-size:0.76rem; }
  .recent-item button { flex-shrink:0; }
  .recent-meta { display:flex; flex-direction:column; gap:0.22rem; min-width:0; }
  .recent-name { color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .recent-sub { color:var(--text-dim); font-size:0.7rem; }
  .empty-state { color:var(--text-dim); font-size:0.75rem; padding:0.5rem 0; }
  .log-box { background:#050508; border:1px solid rgba(0,240,255,0.08); border-radius:4px; padding:1rem; height:180px; overflow-y:auto; font-size:0.72rem; line-height:1.7; margin-top:1rem; }
  .log-line { margin-bottom:0.2rem; }
  .log-line.success { color:var(--success); }
  .log-line.error { color:var(--alert); }
  .log-line.info { color:var(--accent); }
  .log-line.dim { color:var(--text-dim); }
  .log-line.warn { color:#ffaa00; }
  .preview-box { border-radius:6px; overflow:hidden; background:#050508; border:1px solid rgba(0,240,255,0.08); min-height:160px; display:flex; align-items:center; justify-content:center; margin-top:1rem; }
  .preview-box video { width:100%; max-height:320px; display:block; }
  .preview-placeholder { color:var(--text-dim); font-size:0.75rem; letter-spacing:0.1em; }
  .output-path { font-size:0.72rem; color:var(--success); margin-top:0.75rem; padding:0.5rem 0.75rem; background:rgba(0,255,136,0.05); border:1px solid rgba(0,255,136,0.15); border-radius:4px; word-break:break-all; }
  .progress-bar { height:3px; background:rgba(0,240,255,0.1); border-radius:2px; margin-top:1rem; overflow:hidden; }
  .progress-fill { height:100%; background:var(--accent); border-radius:2px; transition:width 0.4s; }
  .position-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:0.4rem; margin-top:0.5rem; }
  .pos-btn { padding:0.5rem; background:#0a0a12; border:1px solid rgba(0,240,255,0.1); border-radius:4px; color:var(--text-dim); font-family:inherit; font-size:0.7rem; cursor:pointer; transition:all 0.2s; text-align:center; }
  .pos-btn:hover { border-color:var(--accent); color:var(--accent); }
  .pos-btn.active { background:rgba(0,240,255,0.1); border-color:var(--accent); color:var(--accent); }
  .stat { display:flex; justify-content:space-between; font-size:0.75rem; padding:0.4rem 0; border-bottom:1px solid rgba(255,255,255,0.04); }
  .stat-val { color:var(--accent); }
  .reel-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:0.75rem; margin-top:1rem; }
  .reel-card { background:#0a0a12; border:1px solid rgba(0,240,255,0.1); border-radius:6px; overflow:hidden; transition:all 0.2s; }
  .reel-card:hover { border-color:var(--accent); transform:translateY(-2px); }
  .reel-card video { width:100%; display:block; max-height:200px; }
  .reel-label { padding:0.4rem 0.5rem; font-size:0.68rem; color:var(--text-dim); }
  .yt-thumb { width:100%; border-radius:6px; overflow:hidden; margin-top:1rem; background:#050508; border:1px solid rgba(0,240,255,0.08); }
  .yt-thumb img { width:100%; display:block; }
  .yt-info { padding:0.75rem; }
  .yt-title { font-size:0.8rem; margin-bottom:0.3rem; }
  .yt-meta { font-size:0.7rem; color:var(--text-dim); }
  .badge { display:inline-block; padding:0.2rem 0.5rem; border-radius:3px; font-size:0.65rem; letter-spacing:0.1em; }
  .badge.live { background:rgba(255,42,109,0.15); color:var(--alert); border:1px solid rgba(255,42,109,0.3); }
  .badge.ready { background:rgba(0,255,136,0.1); color:var(--success); border:1px solid rgba(0,255,136,0.2); }
  .cut-row { display:flex; gap:0.5rem; align-items:center; margin-bottom:0.5rem; }
  .cut-row input { flex:1; }
  .cut-remove { background:none; border:1px solid rgba(255,42,109,0.3); color:var(--alert); border-radius:4px; padding:0.3rem 0.6rem; cursor:pointer; font-family:inherit; font-size:0.7rem; }
  .directory-note { margin-top:0.75rem; font-size:0.7rem; color:var(--text-dim); line-height:1.5; }
  .scanline { position:fixed; top:0; left:0; width:100%; height:3px; background:linear-gradient(90deg,transparent,var(--accent),transparent); opacity:0.4; pointer-events:none; z-index:100; animation:scan 8s linear infinite; }
  @keyframes scan { 0%{transform:translateY(-100vh)} 100%{transform:translateY(100vh)} }
  @media (max-width: 1024px) {
    .status-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  }
  @media (max-width: 768px) {
    body { padding:1rem; }
    header { flex-direction:column; align-items:flex-start; gap:1rem; }
    .header-meta { align-items:flex-start; width:100%; }
    .tabs { overflow:auto; }
    .layout, .layout-3, .status-grid { grid-template-columns:1fr; }
    .card-title-row, .recent-item { align-items:flex-start; flex-direction:column; }
    .recent-item button { width:100%; }
  }
  ::-webkit-scrollbar { width:4px; } ::-webkit-scrollbar-track { background:transparent; } ::-webkit-scrollbar-thumb { background:rgba(0,240,255,0.2); border-radius:2px; }
</style>
</head>
<body>
<div class="grid-bg"></div>
<div class="scanline"></div>

<header>
  <div class="logo">NEXUS</div>
  <div class="header-meta">
    <div class="subtitle">VIDEO EDITOR // FFMPEG INTERFACE</div>
    <button class="chip-btn" type="button" onclick="refreshWorkspace().catch(error => console.error(error))">↻ Refresh Workspace</button>
  </div>
</header>

<div class="tabs">
  <div class="tab active" onclick="switchTab('editor')">▶ Logo Editor</div>
  <div class="tab" onclick="switchTab('reels')">✂ YouTube → Reels</div>
</div>

<div class="status-grid" id="workspaceStatus">
  <div class="status-card">
    <div class="status-head">
      <span class="status-label">Workspace</span>
      <span class="status-pill warn">Loading</span>
    </div>
    <div class="status-value">--</div>
    <div class="status-note">Checking tools, source clips, and recent outputs.</div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════
     TAB 1 — LOGO EDITOR
════════════════════════════════════════════════ -->
<div id="tab-editor" class="tab-content active">
<div class="layout">
  <div class="col">
    <div class="card">
      <div class="card-title-row">
        <div class="card-title">Select Video</div>
        <button class="chip-btn small" type="button" onclick="refreshWorkspace().catch(error => console.error(error))">Refresh Clips</button>
      </div>
      <div class="file-list" id="fileList">Loading...</div>
      <div class="directory-note" id="sourceDirectoryNote"></div>
    </div>
    <div class="card">
      <div class="card-title">Video Info</div>
      <div class="stat"><span>File</span><span class="stat-val" id="statFile">—</span></div>
      <div class="stat"><span>Resolution</span><span class="stat-val" id="statRes">—</span></div>
      <div class="stat"><span>Duration</span><span class="stat-val" id="statDur">—</span></div>
      <div class="stat"><span>Size</span><span class="stat-val" id="statSize">—</span></div>
    </div>
    <div class="card">
      <div class="card-title">Source Preview</div>
      <div class="preview-box" id="previewBox"><span class="preview-placeholder">NO FILE SELECTED</span></div>
    </div>
  </div>

  <div class="col">
    <div class="card">
      <div class="card-title">Logo Settings</div>
      <label>Position</label>
      <div class="position-grid">
        <button class="pos-btn" onclick="setPos('top-left',this)">↖ TL</button>
        <button class="pos-btn" onclick="setPos('top-center',this)">↑ TC</button>
        <button class="pos-btn" onclick="setPos('top-right',this)">↗ TR</button>
        <button class="pos-btn" onclick="setPos('center-left',this)">← CL</button>
        <button class="pos-btn active" onclick="setPos('center',this)">● CTR</button>
        <button class="pos-btn" onclick="setPos('center-right',this)">→ CR</button>
        <button class="pos-btn" onclick="setPos('bottom-left',this)">↙ BL</button>
        <button class="pos-btn" onclick="setPos('bottom-center',this)">↓ BC</button>
        <button class="pos-btn" onclick="setPos('bottom-right',this)">↘ BR</button>
      </div>
      <label>Logo Size — <span id="sizeVal">600</span>px</label>
      <input type="range" id="logoSize" min="200" max="1400" value="600" step="50" oninput="document.getElementById('sizeVal').textContent=this.value">
      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="fadeToggle" checked><span class="slider-toggle"></span></label>
        <span class="toggle-label">Fade In</span>
      </div>
      <div id="fadeOptions">
        <label>Appears in last — <span id="fadeStartVal">3</span>s</label>
        <input type="range" id="fadeDuration" min="1" max="8" value="3" step="0.5" oninput="document.getElementById('fadeStartVal').textContent=this.value">
        <label>Fade length — <span id="fadeLenVal">2</span>s</label>
        <input type="range" id="fadeLen" min="0.5" max="5" value="2" step="0.5" oninput="document.getElementById('fadeLenVal').textContent=this.value">
      </div>
      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="bgToggle"><span class="slider-toggle"></span></label>
        <span class="toggle-label">Dark Background Behind Logo</span>
      </div>
      <div class="toggle-row" style="margin-top:1rem;">
        <label class="toggle"><input type="checkbox" id="ghostToggle"><span class="slider-toggle"></span></label>
        <span class="toggle-label">Ghost Logo (washed out)</span>
      </div>
      <div id="ghostOptions" style="opacity:0.3;pointer-events:none;margin-top:1rem;">
        <label>Ghost Size — <span id="ghostSizeVal">1000</span>px</label>
        <input type="range" id="ghostSize" min="300" max="2400" value="1000" step="50" oninput="document.getElementById('ghostSizeVal').textContent=this.value">
        <label>Opacity — <span id="ghostOpacVal">12</span>%</label>
        <input type="range" id="ghostOpac" min="3" max="50" value="12" step="1" oninput="document.getElementById('ghostOpacVal').textContent=this.value">
        <label>Ghost Position</label>
        <div class="position-grid">
          <button class="pos-btn" onclick="setGhostPos('top-left',this)">↖ TL</button>
          <button class="pos-btn" onclick="setGhostPos('top-center',this)">↑ TC</button>
          <button class="pos-btn" onclick="setGhostPos('top-right',this)">↗ TR</button>
          <button class="pos-btn" onclick="setGhostPos('center-left',this)">← CL</button>
          <button class="pos-btn active" onclick="setGhostPos('center',this)">● CTR</button>
          <button class="pos-btn" onclick="setGhostPos('center-right',this)">→ CR</button>
          <button class="pos-btn" onclick="setGhostPos('bottom-left',this)">↙ BL</button>
          <button class="pos-btn" onclick="setGhostPos('bottom-center',this)">↓ BC</button>
          <button class="pos-btn" onclick="setGhostPos('bottom-right',this)">↘ BR</button>
        </div>
        <div class="toggle-row" style="margin-top:1rem;">
          <label class="toggle"><input type="checkbox" id="ghostFadeToggle"><span class="slider-toggle"></span></label>
          <span class="toggle-label">Timed Appearance</span>
        </div>
        <div id="ghostFadeOptions" style="opacity:0.3;pointer-events:none;margin-top:0.5rem;">
          <label>Appears in last — <span id="ghostStartVal">3</span>s</label>
          <input type="range" id="ghostFadeStart" min="1" max="15" value="3" step="0.5" oninput="document.getElementById('ghostStartVal').textContent=this.value">
          <label>Fade length — <span id="ghostFadeLenVal">1.5</span>s</label>
          <input type="range" id="ghostFadeLen" min="0.5" max="5" value="1.5" step="0.5" oninput="document.getElementById('ghostFadeLenVal').textContent=this.value">
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">CTA Overlay</div>
      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="ctaToggle"><span class="slider-toggle"></span></label>
        <span class="toggle-label">Enable CTA at end</span>
      </div>
      <div id="ctaOptions" style="opacity:0.3;pointer-events:none;margin-top:1rem;">
        <label>CTA Text</label>
        <input type="text" id="ctaText" value="@viviandco" placeholder="Shop Now / @handle">
        <label>Effect</label>
        <select id="ctaEffect">
          <option value="slide">Slide Up</option>
          <option value="fade">Fade In</option>
        </select>
        <div class="toggle-row">
          <label class="toggle"><input type="checkbox" id="ctaArrow" checked><span class="slider-toggle"></span></label>
          <span class="toggle-label">Animated ↑ arrow</span>
        </div>
        <div class="toggle-row">
          <label class="toggle"><input type="checkbox" id="ctaPill"><span class="slider-toggle"></span></label>
          <span class="toggle-label">Pill background</span>
        </div>
        <label>Appears in last — <span id="ctaStartVal">3</span>s</label>
        <input type="range" id="ctaStart" min="1" max="10" value="3" step="0.5" oninput="document.getElementById('ctaStartVal').textContent=this.value">
      </div>
    </div>
    <div class="card">
      <div class="card-title">Render</div>
      <button class="btn" id="renderBtn" onclick="renderLogo()">▶ RENDER VIDEO</button>
      <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
      <div class="log-box" id="logBox"><div class="log-line dim">// Ready — select a video and hit render</div></div>
      <div id="outputPath"></div>
    </div>
    <div class="card">
      <div class="card-title">Output Preview</div>
      <div class="preview-box" id="outputPreviewBox"><span class="preview-placeholder">OUTPUT WILL APPEAR HERE</span></div>
      <div class="recent-list" id="recentEditedList"></div>
    </div>
  </div>
</div>
</div>

<!-- ═══════════════════════════════════════════════
     TAB 2 — YOUTUBE → REELS
════════════════════════════════════════════════ -->
<div id="tab-reels" class="tab-content">
<div class="layout">
  <div class="col">
    <div class="card">
      <div class="card-title">YouTube Video</div>
      <label>YouTube URL</label>
      <input type="url" id="ytUrl" placeholder="https://www.youtube.com/watch?v=...">
      <button class="btn" onclick="fetchInfo()">⟳ FETCH INFO</button>
      <div id="ytPreview"></div>
    </div>

    <div class="card">
      <div class="card-title">Cut Settings</div>
      <label>Reel Duration</label>
      <select id="reelDuration">
        <option value="15">15 seconds</option>
        <option value="30" selected>30 seconds</option>
        <option value="45">45 seconds</option>
        <option value="60">60 seconds</option>
        <option value="90">90 seconds</option>
      </select>

      <label style="margin-top:1rem;">Cut Mode</label>
      <select id="cutMode" onchange="toggleCutMode()">
        <option value="auto">Auto — split entire video evenly</option>
        <option value="manual">Manual — define cut points</option>
      </select>

      <div id="manualCuts" style="display:none;margin-top:1rem;">
        <label>Cut Points (start–end in seconds)</label>
        <div id="cutList"></div>
        <button class="btn" style="margin-top:0.5rem;" onclick="addCut()">+ ADD CUT</button>
      </div>

      <div class="toggle-row" style="margin-top:1.5rem;">
        <label class="toggle"><input type="checkbox" id="reelLogoToggle" checked><span class="slider-toggle"></span></label>
        <span class="toggle-label">Add Vivi&Co Logo</span>
      </div>
      <div id="reelLogoOptions">
        <label>Logo Position</label>
        <div class="position-grid">
          <button class="pos-btn" onclick="setReelPos('top-left',this)">↖ TL</button>
          <button class="pos-btn active" onclick="setReelPos('top-center',this)">↑ TC</button>
          <button class="pos-btn" onclick="setReelPos('top-right',this)">↗ TR</button>
          <button class="pos-btn" onclick="setReelPos('center-left',this)">← CL</button>
          <button class="pos-btn" onclick="setReelPos('center',this)">● CTR</button>
          <button class="pos-btn" onclick="setReelPos('center-right',this)">→ CR</button>
          <button class="pos-btn" onclick="setReelPos('bottom-left',this)">↙ BL</button>
          <button class="pos-btn" onclick="setReelPos('bottom-center',this)">↓ BC</button>
          <button class="pos-btn" onclick="setReelPos('bottom-right',this)">↘ BR</button>
        </div>
      </div>

      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="reelCropToggle" checked><span class="slider-toggle"></span></label>
        <span class="toggle-label">Crop to 9:16 (portrait reels)</span>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Captions</div>
      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="captionToggle"><span class="slider-toggle"></span></label>
        <span class="toggle-label">Auto Captions</span>
      </div>
      <div id="captionOptions" style="opacity:0.3;pointer-events:none;margin-top:1rem;">
        <label>Language</label>
        <input type="text" id="captionLang" value="en" placeholder="en, es, fr, ar...">
        <label>Font Size — <span id="captionSizeVal">22</span>px</label>
        <input type="range" id="captionSize" min="12" max="56" value="22" step="1" oninput="document.getElementById('captionSizeVal').textContent=this.value">
        <label>Position</label>
        <select id="captionPos">
          <option value="2">Bottom Center</option>
          <option value="8">Top Center</option>
        </select>
        <div class="toggle-row">
          <label class="toggle"><input type="checkbox" id="captionBox" checked><span class="slider-toggle"></span></label>
          <span class="toggle-label">Background box</span>
        </div>
      </div>
    </div>
  </div>

  <div class="col">
    <div class="card">
      <div class="card-title">Download & Cut</div>
      <button class="btn" id="reelBtn" onclick="startReels()">▶ DOWNLOAD & CUT REELS</button>
      <div class="progress-bar"><div class="progress-fill" id="reelProgress" style="width:0%"></div></div>
      <div class="log-box" id="reelLog"><div class="log-line dim">// Paste a YouTube URL and hit go</div></div>
    </div>

    <div class="card">
      <div class="card-title">Output Reels</div>
      <div id="reelOutput"><div class="preview-placeholder" style="padding:2rem;text-align:center;">Reels will appear here</div></div>
      <div class="recent-list" id="recentReelsList"></div>
    </div>
  </div>
</div>
</div>

<script>
// ─── Tab switching ───────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['editor','reels'][i] === name));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
}

// ─── Logo Editor ─────────────────────────────────
let selectedFile = null, videoDuration = 0, position = 'center', ghostPosition = 'center';

function setGhostPos(p, el) {
  ghostPosition = p;
  document.querySelectorAll('#ghostOptions .pos-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function formatLocalTime(ts) {
  if (!ts) return 'Unknown time';
  return new Date(ts * 1000).toLocaleString();
}

function renderRecentList(containerId, items, emptyLabel) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = `<div class="empty-state">${emptyLabel}</div>`;
    return;
  }
  container.innerHTML = items.map(item => `
    <div class="recent-item">
      <div class="recent-meta">
        <div class="recent-name">${item.name}</div>
        <div class="recent-sub">${item.size} · ${formatLocalTime(item.mtime)}</div>
      </div>
      <button class="chip-btn small" type="button" onclick="previewOutput('${item.path.replace(/'/g,"\\'")}')">Preview</button>
    </div>
  `).join('');
}

function previewOutput(path) {
  const target = path.toLowerCase().includes('/reels/') ? document.getElementById('reelOutput') : document.getElementById('outputPreviewBox');
  if (!target) return;
  target.innerHTML = `<video controls src="/video?path=${encodeURIComponent(path)}"></video>`;
}

async function loadWorkspaceStatus() {
  const r = await fetch('/status');
  const data = await r.json();
  const tools = data.tools || {};
  const counts = data.counts || {};
  const toolReady = Object.values(tools).every(Boolean);
  document.getElementById('workspaceStatus').innerHTML = `
    <div class="status-card">
      <div class="status-head">
        <span class="status-label">Source Clips</span>
        <span class="status-pill ${counts.source ? 'ok' : 'warn'}">${counts.source ? 'Ready' : 'Empty'}</span>
      </div>
      <div class="status-value">${counts.source || 0}</div>
      <div class="status-note">${(data.directories || {}).source || ''}</div>
    </div>
    <div class="status-card">
      <div class="status-head">
        <span class="status-label">Edited Renders</span>
        <span class="status-pill ${(counts.edited || 0) ? 'ok' : 'warn'}">${(counts.edited || 0) ? 'Active' : 'Waiting'}</span>
      </div>
      <div class="status-value">${counts.edited || 0}</div>
      <div class="status-note">${(data.directories || {}).edited || ''}</div>
    </div>
    <div class="status-card">
      <div class="status-head">
        <span class="status-label">Reels Output</span>
        <span class="status-pill ${(counts.reels || 0) ? 'ok' : 'warn'}">${(counts.reels || 0) ? 'Active' : 'Empty'}</span>
      </div>
      <div class="status-value">${counts.reels || 0}</div>
      <div class="status-note">${(data.directories || {}).reels || ''}</div>
    </div>
    <div class="status-card">
      <div class="status-head">
        <span class="status-label">Toolchain</span>
        <span class="status-pill ${toolReady ? 'ok' : 'danger'}">${toolReady ? 'Ready' : 'Needs Fix'}</span>
      </div>
      <div class="status-value">${Object.values(tools).filter(Boolean).length}/4</div>
      <div class="status-note">ffmpeg ${tools.ffmpeg ? '✓' : '×'} · ffprobe ${tools.ffprobe ? '✓' : '×'} · yt-dlp ${tools.yt_dlp ? '✓' : '×'} · overlay ${tools.overlay ? '✓' : '×'}</div>
    </div>
  `;
  const note = document.getElementById('sourceDirectoryNote');
  if (note) {
    note.textContent = `Watching ${counts.source || 0} source clips in ${(data.directories || {}).source || ''}`;
  }
}

async function loadRecentOutputs() {
  const r = await fetch('/outputs');
  const data = await r.json();
  renderRecentList('recentEditedList', data.edited || [], 'No recent renders yet.');
  renderRecentList('recentReelsList', data.reels || [], 'No recent reels yet.');
}

async function refreshWorkspace() {
  await Promise.all([loadFiles(), loadWorkspaceStatus(), loadRecentOutputs()]);
}

async function loadFiles() {
  const r = await fetch('/files');
  const files = await r.json();
  const list = document.getElementById('fileList');
  if (!files.length) { list.innerHTML = '<div class="empty-state">No source videos found in the CapCut folder.</div>'; return; }
  list.innerHTML = files.map(f => `
    <div class="file-item ${selectedFile === f.path ? 'selected' : ''}" onclick="selectFile('${f.path.replace(/'/g,"\\'")}','${f.name.replace(/'/g,"\\'")}','${f.size}',this)">
      <span>${f.name}</span><span class="file-size">${f.size}</span>
    </div>`).join('');
}

async function selectFile(path, name, size, el) {
  selectedFile = path;
  document.querySelectorAll('.file-item').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('statFile').textContent = name;
  document.getElementById('statSize').textContent = size;
  const info = await fetch('/info', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})}).then(r=>r.json());
  if (info.error) {
    editorLog('Info error: ' + info.error, 'error');
  } else if (info.width) {
    document.getElementById('statRes').textContent = info.width + 'x' + info.height;
    document.getElementById('statDur').textContent = parseFloat(info.duration).toFixed(1) + 's';
    videoDuration = parseFloat(info.duration);
  }
  document.getElementById('previewBox').innerHTML = `<video controls src="/video?path=${encodeURIComponent(path)}"></video>`;
}

function setPos(p, el) {
  position = p;
  document.querySelectorAll('#tab-editor .pos-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function editorLog(msg, type='dim') {
  const box = document.getElementById('logBox');
  const line = document.createElement('div');
  line.className = 'log-line ' + type;
  line.textContent = '[' + new Date().toLocaleTimeString('en-US',{hour12:false}) + '] ' + msg;
  box.appendChild(line); box.scrollTop = box.scrollHeight;
}

async function renderLogo() {
  if (!selectedFile) { editorLog('No file selected','error'); return; }
  const btn = document.getElementById('renderBtn');
  btn.disabled = true; btn.textContent = '⟳ RENDERING...';
  document.getElementById('progressFill').style.width = '15%';
  editorLog('Starting render...','info');
  const payload = {
    path: selectedFile, position,
    logo_size: parseInt(document.getElementById('logoSize').value),
    fade: document.getElementById('fadeToggle').checked,
    fade_duration: parseFloat(document.getElementById('fadeDuration').value),
    fade_len: parseFloat(document.getElementById('fadeLen').value),
    bg: document.getElementById('bgToggle').checked,
    video_duration: videoDuration,
    cta: document.getElementById('ctaToggle').checked,
    cta_text: document.getElementById('ctaText').value,
    cta_effect: document.getElementById('ctaEffect').value,
    cta_arrow: document.getElementById('ctaArrow').checked,
    cta_pill: document.getElementById('ctaPill').checked,
    cta_start: parseFloat(document.getElementById('ctaStart').value),
    ghost: document.getElementById('ghostToggle').checked,
    ghost_size: parseInt(document.getElementById('ghostSize').value),
    ghost_opacity: parseInt(document.getElementById('ghostOpac').value) / 100,
    ghost_position: ghostPosition,
    ghost_fade: document.getElementById('ghostFadeToggle').checked,
    ghost_start_offset: parseFloat(document.getElementById('ghostFadeStart').value),
    ghost_fade_len: parseFloat(document.getElementById('ghostFadeLen').value),
  };
  document.getElementById('progressFill').style.width = '40%';
  const r = await fetch('/render', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result = await r.json();
  document.getElementById('progressFill').style.width = '100%';
  if (result.ok) {
    editorLog('Done: ' + result.output,'success');
    document.getElementById('outputPath').innerHTML = '<div class="output-path">✓ ' + result.output + '</div>';
    document.getElementById('outputPreviewBox').innerHTML = `<video controls src="/video?path=${encodeURIComponent(result.output)}"></video>`;
    await refreshWorkspace().catch(error => editorLog('Workspace refresh failed: ' + error.message, 'warn'));
  } else {
    editorLog('Error: ' + result.error,'error');
  }
  btn.disabled = false; btn.textContent = '▶ RENDER VIDEO';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('fadeToggle').addEventListener('change', function() {
    document.getElementById('fadeOptions').style.opacity = this.checked ? '1' : '0.3';
    document.getElementById('fadeOptions').style.pointerEvents = this.checked ? 'all' : 'none';
  });
  document.getElementById('ghostFadeToggle').addEventListener('change', function() {
    document.getElementById('ghostFadeOptions').style.opacity = this.checked ? '1' : '0.3';
    document.getElementById('ghostFadeOptions').style.pointerEvents = this.checked ? 'all' : 'none';
  });
  document.getElementById('ghostToggle').addEventListener('change', function() {
    document.getElementById('ghostOptions').style.opacity = this.checked ? '1' : '0.3';
    document.getElementById('ghostOptions').style.pointerEvents = this.checked ? 'all' : 'none';
  });
  document.getElementById('ctaToggle').addEventListener('change', function() {
    document.getElementById('ctaOptions').style.opacity = this.checked ? '1' : '0.3';
    document.getElementById('ctaOptions').style.pointerEvents = this.checked ? 'all' : 'none';
  });
  refreshWorkspace().catch(error => editorLog('Workspace load failed: ' + error.message, 'error'));
});

// ─── YouTube Reels ────────────────────────────────
let reelPosition = 'top-center';
let ytDuration = 0;

function setReelPos(p, el) {
  reelPosition = p;
  document.querySelectorAll('#tab-reels .pos-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function toggleCutMode() {
  const manual = document.getElementById('cutMode').value === 'manual';
  document.getElementById('manualCuts').style.display = manual ? 'block' : 'none';
}

function addCut() {
  const list = document.getElementById('cutList');
  const idx = list.children.length;
  const row = document.createElement('div');
  row.className = 'cut-row';
  row.innerHTML = `
    <input type="number" placeholder="Start (s)" step="0.1" min="0" id="cut_start_${idx}">
    <span style="color:var(--text-dim);font-size:0.8rem;">→</span>
    <input type="number" placeholder="End (s)" step="0.1" min="0" id="cut_end_${idx}">
    <button class="cut-remove" onclick="this.parentElement.remove()">✕</button>`;
  list.appendChild(row);
}

function reelLog(msg, type='dim') {
  const box = document.getElementById('reelLog');
  const line = document.createElement('div');
  line.className = 'log-line ' + type;
  line.textContent = '[' + new Date().toLocaleTimeString('en-US',{hour12:false}) + '] ' + msg;
  box.appendChild(line); box.scrollTop = box.scrollHeight;
}

async function fetchInfo() {
  const url = document.getElementById('ytUrl').value.trim();
  if (!url) { reelLog('Enter a YouTube URL first','error'); return; }
  reelLog('Fetching video info...','info');
  const r = await fetch('/yt_info', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  const info = await r.json();
  if (info.error) { reelLog('Error: ' + info.error,'error'); return; }
  ytDuration = info.duration || 0;
  document.getElementById('ytPreview').innerHTML = `
    <div class="yt-thumb">
      ${info.thumbnail ? `<img src="${info.thumbnail}" alt="thumbnail">` : ''}
      <div class="yt-info">
        <div class="yt-title">${info.title || 'Unknown'}</div>
        <div class="yt-meta">${info.uploader || ''} • ${Math.floor(ytDuration/60)}:${String(Math.floor(ytDuration%60)).padStart(2,'0')} • ${info.view_count ? Number(info.view_count).toLocaleString() + ' views' : ''}</div>
      </div>
    </div>`;
  reelLog('Found: ' + (info.title || url), 'success');
}

async function startReels() {
  const url = document.getElementById('ytUrl').value.trim();
  if (!url) { reelLog('Enter a YouTube URL','error'); return; }
  const btn = document.getElementById('reelBtn');
  btn.disabled = true; btn.textContent = '⟳ WORKING...';
  document.getElementById('reelProgress').style.width = '5%';
  document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder" style="padding:2rem;text-align:center;">Processing...</div>';

  const manualCuts = [];
  if (document.getElementById('cutMode').value === 'manual') {
    const rows = document.getElementById('cutList').children;
    for (let i = 0; i < rows.length; i++) {
      const s = parseFloat(document.getElementById('cut_start_' + i)?.value);
      const e = parseFloat(document.getElementById('cut_end_' + i)?.value);
      if (!isNaN(s) && !isNaN(e) && e > s) manualCuts.push({start: s, end: e});
    }
  }

  const payload = {
    url,
    reel_duration: parseInt(document.getElementById('reelDuration').value),
    cut_mode: document.getElementById('cutMode').value,
    manual_cuts: manualCuts,
    add_logo: document.getElementById('reelLogoToggle').checked,
    logo_position: reelPosition,
    crop_portrait: document.getElementById('reelCropToggle').checked,
    add_captions: document.getElementById('captionToggle').checked,
    caption_lang: document.getElementById('captionLang').value.trim() || 'en',
    caption_fontsize: parseInt(document.getElementById('captionSize').value),
    caption_alignment: parseInt(document.getElementById('captionPos').value),
    caption_box: document.getElementById('captionBox').checked,
  };

  reelLog('Downloading...','info');
  document.getElementById('reelProgress').style.width = '20%';

  const r = await fetch('/yt_reels', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result = await r.json();
  document.getElementById('reelProgress').style.width = '100%';

  if (result.ok) {
    reelLog(`Done — ${result.reels.length} reels created`,'success');
    result.reels.forEach((p, i) => reelLog('  Reel ' + (i+1) + ': ' + p, 'dim'));
    document.getElementById('reelOutput').innerHTML = `
      <div class="reel-grid">
        ${result.reels.map((p,i) => `
          <div class="reel-card">
            <video controls src="/video?path=${encodeURIComponent(p)}" loop></video>
            <div class="reel-label">Reel ${i+1}</div>
          </div>`).join('')}
      </div>`;
    await refreshWorkspace().catch(error => reelLog('Workspace refresh failed: ' + error.message, 'warn'));
  } else {
    reelLog('Error: ' + result.error,'error');
    document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder" style="padding:2rem;text-align:center;color:var(--alert);">FAILED</div>';
  }

  btn.disabled = false; btn.textContent = '▶ DOWNLOAD & CUT REELS';
}
</script>
</body>
</html>
"""

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/status')
def status():
    return jsonify(get_workspace_snapshot())

@app.route('/health')
def health():
    snapshot = get_workspace_snapshot()
    return jsonify({
        "ok": snapshot["ready"],
        "port": PORT,
        "tools": snapshot["tools"],
        "tool_versions": snapshot["tool_versions"],
        "directories": snapshot["directories"],
        "overlay": snapshot["config"]["overlay"],
    }), (200 if snapshot["ready"] else 503)

@app.route('/outputs')
def outputs():
    return jsonify(get_workspace_snapshot()["recent_outputs"])

@app.route('/files')
def list_files():
    return jsonify(list_videos(CAPCUT_DIR))

@app.route('/info', methods=['POST'])
def video_info():
    path = resolve_media_path((request.json or {}).get('path',''))
    if not path:
        return jsonify({'error':'Invalid or unsupported video path'}), 400
    if not os.path.exists(FFPROBE):
        return jsonify({'error':'ffprobe is not available on this machine'}), 503
    try:
        r = subprocess.run([FFPROBE,'-v','quiet','-select_streams','v:0',
            '-show_entries','stream=width,height','-show_entries','format=duration',
            '-of','json', path], capture_output=True, text=True)
        data = json.loads(r.stdout)
        stream = data.get('streams',[{}])[0]
        fmt = data.get('format',{})
        return jsonify({'width':stream.get('width'),'height':stream.get('height'),'duration':fmt.get('duration',0)})
    except Exception as e:
        return jsonify({'error':str(e)})

@app.route('/video')
def serve_video():
    path = resolve_media_path(request.args.get('path',''))
    if path:
        return send_file(path, conditional=True)
    return 'Not found', 404

@app.route('/render', methods=['POST'])
def render_video():
    data = request.json or {}
    path = resolve_media_path(data.get('path'))
    if not path:
        return jsonify({'ok':False,'error':'Pick a valid source video from the workspace first'}), 400
    if not os.path.exists(FFMPEG):
        return jsonify({'ok':False,'error':'ffmpeg is not available on this machine'}), 503
    if not os.path.exists(OVERLAY):
        return jsonify({'ok':False,'error':'Overlay asset is missing'}), 503
    position = data.get('position','center')
    logo_size = data.get('logo_size', 600)
    fade = data.get('fade', True)
    fade_duration = data.get('fade_duration', 3.0)
    fade_len = data.get('fade_len', 2.0)
    bg = data.get('bg', False)
    duration = float(data.get('video_duration', 0))
    cta = data.get('cta', False)
    cta_text = data.get('cta_text', '@viviandco')
    cta_effect = data.get('cta_effect', 'slide')
    cta_arrow = data.get('cta_arrow', True)
    cta_pill = data.get('cta_pill', False)
    cta_start_offset = float(data.get('cta_start', 3.0))
    ghost = data.get('ghost', False)
    ghost_size = int(data.get('ghost_size', 1000))
    ghost_opacity = float(data.get('ghost_opacity', 0.12))
    ghost_position = data.get('ghost_position', 'center')
    ghost_fade = data.get('ghost_fade', False)
    ghost_start_offset = float(data.get('ghost_start_offset', 3.0))
    ghost_fade_len = float(data.get('ghost_fade_len', 1.5))

    pos_map = {
        'top-left':     'x=W*0.03:y=H*0.04',
        'top-center':   'x=(W-w)/2:y=H*0.04',
        'top-right':    'x=W-w-W*0.03:y=H*0.04',
        'center-left':  'x=W*0.03:y=(H-h)/2',
        'center':       'x=(W-w)/2:y=(H-h)/2',
        'center-right': 'x=W-w-W*0.03:y=(H-h)/2',
        'bottom-left':  'x=W*0.03:y=H-h-H*0.04',
        'bottom-center':'x=(W-w)/2:y=H-h-H*0.04',
        'bottom-right': 'x=W-w-W*0.03:y=H-h-H*0.04',
    }
    overlay_pos = pos_map.get(position, 'x=(W-w)/2:y=H*0.04')

    logo_chain = f"[1:v]crop=615:188:132:1827,scale={logo_size}:-1,format=rgba"
    if bg:
        logo_chain += ",pad=w=iw+40:h=ih+24:x=20:y=12:color=black@0.5"
    logo_chain += "[logo_scaled]"

    if fade and duration > 0:
        fade_start = max(0, duration - fade_duration)
        logo_chain += f";[logo_scaled]loop=loop=-1:size=1:start=0,trim=end={duration},setpts=PTS-STARTPTS,geq=lum='p(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='clip(((T-{fade_start})/{fade_len})*alpha(X,Y)*255,0,255)'[logo_final]"
    else:
        logo_chain += ";[logo_scaled]null[logo_final]"

    # Ghost logo chain (low-opacity washed-out version layered beneath main logo)
    ghost_pos_str = pos_map.get(ghost_position, 'x=(W-w)/2:y=(H-h)/2')
    if ghost_fade and duration > 0:
        ghost_start = max(0, duration - ghost_start_offset)
        ghost_chain = (
            f"[1:v]crop=615:188:132:1827,scale={ghost_size}:-1,format=rgba,"
            f"colorchannelmixer=aa={ghost_opacity:.3f},"
            f"loop=loop=-1:size=1:start=0,trim=end={duration},setpts=PTS-STARTPTS,"
            f"fade=t=in:st={ghost_start}:d={ghost_fade_len}:alpha=1[ghost_logo]"
        )
    else:
        ghost_chain = (
            f"[1:v]crop=615:188:132:1827,scale={ghost_size}:-1,format=rgba,"
            f"colorchannelmixer=aa={ghost_opacity:.3f}[ghost_logo]"
        )

    base = os.path.splitext(os.path.basename(path))[0]
    output = os.path.join(EDITED_DIR, f"{base}_vivi.mov")

    if cta and duration > 0:
        fs = max(0, duration - cta_start_offset)

        # Font detection
        font = next((p for p in [
            '/System/Library/Fonts/HelveticaNeue.ttc',
            '/Library/Fonts/Arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
        ] if os.path.exists(p)), None)
        font_opt = f"fontfile={font}:" if font else ""

        # Escape CTA text for drawtext (colons and single quotes are special)
        safe_text = cta_text.replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:')

        # Animation expressions — single quotes protect commas from filter parser
        if cta_effect == 'slide':
            y_expr  = f"'(H*0.55-th/2)+120*max(0,1-(t-{fs})/0.7)'"
            a_expr  = f"'clip((t-{fs})/0.7,0,1)'"
        else:  # fade
            y_expr  = "'(H*0.55-th/2)'"
            a_expr  = f"'clip((t-{fs})/1.0,0,1)'"

        box_str = ":box=1:boxcolor=black@0.35:boxborderw=28" if cta_pill else ""

        dt_main = (
            f"drawtext={font_opt}text='{safe_text}':fontsize=88:fontcolor=white"
            f":x='(W-tw)/2':y={y_expr}:alpha={a_expr}{box_str}"
        )
        drawtext_chain = dt_main

        if cta_arrow:
            arr_fs = fs + 0.4
            dt_arrow = (
                f"drawtext={font_opt}text='↑':fontsize=60:fontcolor=white"
                f":x='(W-tw)/2':y='(H*0.55+80)+15*sin(t*5)':alpha='clip((t-{arr_fs})/0.5,0,1)'"
            )
            drawtext_chain += f",{dt_arrow}"

        if ghost:
            filter_complex = (
                f"{ghost_chain};{logo_chain};"
                f"[0:v][ghost_logo]overlay={ghost_pos_str}[vg];"
                f"[vg][logo_final]overlay={overlay_pos}[vlogo]"
                f";[vlogo]{drawtext_chain}[vfinal]"
            )
        else:
            filter_complex = (
                f"{logo_chain};[0:v][logo_final]overlay={overlay_pos}[vlogo]"
                f";[vlogo]{drawtext_chain}[vfinal]"
            )
        cmd = [FFMPEG,'-i',path,'-i',OVERLAY,'-filter_complex',filter_complex,
               '-map','[vfinal]','-map','0:a?',
               '-c:v','libx264','-crf','18','-preset','fast','-c:a','copy',output,'-y']
    else:
        if ghost:
            filter_complex = (
                f"{ghost_chain};{logo_chain};"
                f"[0:v][ghost_logo]overlay={ghost_pos_str}[vg];"
                f"[vg][logo_final]overlay={overlay_pos}[vfinal]"
            )
            cmd = [FFMPEG,'-i',path,'-i',OVERLAY,'-filter_complex',filter_complex,
                   '-map','[vfinal]','-map','0:a?',
                   '-c:v','libx264','-crf','18','-preset','fast','-c:a','copy',output,'-y']
        else:
            filter_complex = f"{logo_chain};[0:v][logo_final]overlay={overlay_pos}"
            cmd = [FFMPEG,'-i',path,'-i',OVERLAY,'-filter_complex',filter_complex,
                   '-c:v','libx264','-crf','18','-preset','fast','-c:a','copy',output,'-y']

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return jsonify({'ok':True,'output':output})
        return jsonify({'ok':False,'error':result.stderr[-600:]})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

@app.route('/yt_info', methods=['POST'])
def yt_info():
    url = (request.json or {}).get('url','').strip()
    if not url:
        return jsonify({'error': 'Enter a YouTube URL first'}), 400
    if not os.path.exists(YTDLP):
        return jsonify({'error': 'yt-dlp is not installed'}), 503
    try:
        r = subprocess.run([YTDLP,'--dump-json','--no-playlist', url],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return jsonify({'error': (r.stderr or 'Could not fetch video info')[-400:]})
        data = json.loads(r.stdout)
        return jsonify({
            'title': data.get('title'),
            'uploader': data.get('uploader'),
            'duration': data.get('duration'),
            'thumbnail': data.get('thumbnail'),
            'view_count': data.get('view_count'),
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/yt_reels', methods=['POST'])
def yt_reels():
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'ok':False,'error':'Enter a YouTube URL first'}), 400
    if not os.path.exists(YTDLP):
        return jsonify({'ok':False,'error':'yt-dlp is not installed'}), 503
    if not os.path.exists(FFMPEG) or not os.path.exists(FFPROBE):
        return jsonify({'ok':False,'error':'ffmpeg and ffprobe are required to cut reels'}), 503
    reel_dur = int(data.get('reel_duration', 30))
    cut_mode = data.get('cut_mode','auto')
    manual_cuts = data.get('manual_cuts',[])
    add_logo = data.get('add_logo', True)
    logo_position = data.get('logo_position','top-center')
    crop_portrait = data.get('crop_portrait', True)
    add_captions = data.get('add_captions', False)
    caption_lang = data.get('caption_lang', 'en')
    caption_fontsize = int(data.get('caption_fontsize', 22))
    caption_alignment = int(data.get('caption_alignment', 2))
    caption_box = data.get('caption_box', True)
    if add_logo and not os.path.exists(OVERLAY):
        return jsonify({'ok':False,'error':'Overlay asset is missing'}), 503

    job_id = str(uuid.uuid4())[:8]
    dl_path = os.path.join(REELS_DIR, f"source_{job_id}.mp4")

    # Download
    dl_cmd = [YTDLP, '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
              '--merge-output-format','mp4', '-o', dl_path, '--no-playlist', url]
    try:
        dl = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
        if dl.returncode != 0:
            return jsonify({'ok':False,'error': dl.stderr[-400:]})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

    # Download auto-captions if requested
    srt_master = None
    if add_captions:
        sub_base = os.path.join(REELS_DIR, f"source_{job_id}")
        sub_cmd = [YTDLP, '--write-auto-subs', '--sub-langs', caption_lang,
                   '--convert-subs', 'srt', '--skip-download',
                   '-o', sub_base, '--no-playlist', url]
        try:
            subprocess.run(sub_cmd, capture_output=True, text=True, timeout=60)
            candidates = glob.glob(f"{sub_base}.*.srt")
            if candidates:
                srt_master = candidates[0]
        except Exception:
            pass

    # Get duration
    try:
        probe = subprocess.run([FFPROBE,'-v','quiet','-show_entries','format=duration','-of','csv=p=0', dl_path],
            capture_output=True, text=True)
        total_dur = float(probe.stdout.strip())
    except:
        total_dur = 0

    # Build cut list
    if cut_mode == 'manual' and manual_cuts:
        cuts = []
        for cut in manual_cuts:
            try:
                start = float(cut['start'])
                end = float(cut['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if end > start >= 0:
                cuts.append((start, end))
        if not cuts:
            return jsonify({'ok':False,'error':'Manual cut points are missing or invalid'}), 400
    else:
        if total_dur <= 0:
            return jsonify({'ok':False,'error':'Could not detect video duration after download'}), 500
        cuts = []
        start = 0.0
        while start < total_dur:
            end = min(start + reel_dur, total_dur)
            if (end - start) >= 1:
                cuts.append((start, end))
            start += reel_dur

    pos_map = {
        'top-left':     'x=W*0.03:y=H*0.04',
        'top-center':   'x=(W-w)/2:y=H*0.04',
        'top-right':    'x=W-w-W*0.03:y=H*0.04',
        'center-left':  'x=W*0.03:y=(H-h)/2',
        'center':       'x=(W-w)/2:y=(H-h)/2',
        'center-right': 'x=W-w-W*0.03:y=(H-h)/2',
        'bottom-left':  'x=W*0.03:y=H-h-H*0.04',
        'bottom-center':'x=(W-w)/2:y=H-h-H*0.04',
        'bottom-right': 'x=W-w-W*0.03:y=H-h-H*0.04',
    }
    overlay_pos = pos_map.get(logo_position, 'x=(W-w)/2:y=H*0.04')

    reels = []
    last_error = None
    for i, (start, end) in enumerate(cuts):
        out = os.path.join(REELS_DIR, f"reel_{job_id}_{i+1:02d}.mp4")
        seg_dur = end - start

        extra_inputs = []
        fc_parts = []
        current_v = "[0:v]"

        # Step 1: portrait crop
        if crop_portrait:
            fc_parts.append(f"{current_v}crop=ih*9/16:ih[vc]")
            current_v = "[vc]"

        # Step 2: logo overlay
        if add_logo:
            extra_inputs += ['-i', OVERLAY]
            overlay_idx = 1  # always index 1 — only one extra input
            logo_chain = "crop=615:188:132:1827,scale=500:-1,format=rgba"
            fc_parts.append(f"[{overlay_idx}:v]{logo_chain}[logo]")
            fc_parts.append(f"{current_v}[logo]overlay={overlay_pos}[vl]")
            current_v = "[vl]"

        # Step 3: burn captions
        if add_captions and srt_master:
            seg_srt = os.path.join('/tmp', f"reel_sub_{job_id}_{i+1:02d}.srt")
            has_subs = trim_srt_segment(srt_master, start, end, seg_srt)
            if has_subs:
                safe_srt = seg_srt.replace("'", "\'")
                bg_style = "BorderStyle=3,BackColour=&H90000000," if caption_box else "OutlineColour=&H00000000,Outline=3,"
                style = f"FontSize={caption_fontsize},PrimaryColour=&H00FFFFFF,{bg_style}Alignment={caption_alignment},MarginV=50,Bold=1"
                fc_parts.append(f"{current_v}subtitles='{safe_srt}':force_style='{style}'[vs]")
                current_v = "[vs]"

        base_inputs = [FFMPEG, '-ss', str(start), '-t', str(seg_dur), '-i', dl_path]
        codec = ['-c:v','libx264','-crf','20','-preset','fast','-c:a','aac','-b:a','128k']

        if fc_parts:
            cmd = base_inputs + extra_inputs + [
                '-filter_complex', ';'.join(fc_parts),
                '-map', current_v, '-map', '0:a?'
            ] + codec + [out, '-y']
        else:
            cmd = base_inputs + codec + [out, '-y']

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(out):
                reels.append(out)
            else:
                last_error = (result.stderr or 'FFmpeg did not write an output file')[-400:]
        except Exception as e:
            last_error = str(e)

    # Cleanup source and temp srt files
    try: os.remove(dl_path)
    except: pass
    if srt_master:
        try: os.remove(srt_master)
        except: pass
    for f in glob.glob(f"/tmp/reel_sub_{job_id}_*.srt"):
        try: os.remove(f)
        except: pass

    if reels:
        return jsonify({'ok':True,'reels':reels})
    return jsonify({'ok':False,'error': last_error or 'No reels were created'})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=PORT, debug=False)
