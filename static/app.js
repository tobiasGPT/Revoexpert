let selectedFile = null;
let videoDuration = 0;
let position = 'center';
let ghostPosition = 'center';
let reelPosition = 'top-center';
let ytDuration = 0;

function readJson(response) {
  return response.json().catch(() => ({}));
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((tab, index) => {
    tab.classList.toggle('active', ['editor', 'reels'][index] === name);
  });
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
}

function setTogglePanel(toggleId, panelId) {
  const toggle = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  if (!toggle || !panel) return;
  panel.style.opacity = toggle.checked ? '1' : '0.3';
  panel.style.pointerEvents = toggle.checked ? 'all' : 'none';
}

function bindTogglePanel(toggleId, panelId) {
  const toggle = document.getElementById(toggleId);
  if (!toggle) return;
  toggle.addEventListener('change', () => setTogglePanel(toggleId, panelId));
  setTogglePanel(toggleId, panelId);
}

function formatLocalTime(ts) {
  if (!ts) return 'Unknown time';
  return new Date(ts * 1000).toLocaleString();
}

function previewOutput(path) {
  const target = path.toLowerCase().includes('/reels/')
    ? document.getElementById('reelOutput')
    : document.getElementById('outputPreviewBox');
  if (!target) return;
  target.innerHTML = `<video controls src="/video?path=${encodeURIComponent(path)}"></video>`;
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
      <button class="chip-btn small" type="button" onclick="previewOutput('${item.path.replace(/'/g, "\\'")}')">Preview</button>
    </div>
  `).join('');
}

async function loadWorkspaceStatus() {
  const response = await fetch('/status');
  const data = await readJson(response);
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
  const response = await fetch('/outputs');
  const data = await readJson(response);
  renderRecentList('recentEditedList', data.edited || [], 'No recent renders yet.');
  renderRecentList('recentReelsList', data.reels || [], 'No recent reels yet.');
}

async function loadFiles() {
  const response = await fetch('/files');
  const files = await readJson(response);
  const list = document.getElementById('fileList');
  if (!files.length) {
    list.innerHTML = '<div class="empty-state">No source videos found in the CapCut folder.</div>';
    return;
  }
  list.innerHTML = files.map(file => `
    <div class="file-item ${selectedFile === file.path ? 'selected' : ''}" onclick="selectFile('${file.path.replace(/'/g, "\\'")}', '${file.name.replace(/'/g, "\\'")}', '${file.size}', this)">
      <span>${file.name}</span><span class="file-size">${file.size}</span>
    </div>
  `).join('');
}

async function refreshWorkspace() {
  await Promise.all([loadFiles(), loadWorkspaceStatus(), loadRecentOutputs()]);
}

async function selectFile(path, name, size, el) {
  selectedFile = path;
  document.querySelectorAll('.file-item').forEach(item => item.classList.remove('selected'));
  if (el) el.classList.add('selected');
  document.getElementById('statFile').textContent = name;
  document.getElementById('statSize').textContent = size;

  const response = await fetch('/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  const info = await readJson(response);
  if (info.error) {
    editorLog(`Info error: ${info.error}`, 'error');
  } else if (info.width) {
    document.getElementById('statRes').textContent = `${info.width}x${info.height}`;
    document.getElementById('statDur').textContent = `${parseFloat(info.duration).toFixed(1)}s`;
    videoDuration = parseFloat(info.duration);
  }
  document.getElementById('previewBox').innerHTML = `<video controls src="/video?path=${encodeURIComponent(path)}"></video>`;
}

function setPos(nextPosition, el) {
  position = nextPosition;
  document.querySelectorAll('#logoPositionGrid .pos-btn').forEach(button => button.classList.remove('active'));
  if (el) el.classList.add('active');
}

function setGhostPos(nextPosition, el) {
  ghostPosition = nextPosition;
  document.querySelectorAll('#ghostPositionGrid .pos-btn').forEach(button => button.classList.remove('active'));
  if (el) el.classList.add('active');
}

function setReelPos(nextPosition, el) {
  reelPosition = nextPosition;
  document.querySelectorAll('#reelPositionGrid .pos-btn').forEach(button => button.classList.remove('active'));
  if (el) el.classList.add('active');
}

function editorLog(message, type = 'dim') {
  const box = document.getElementById('logBox');
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString('en-US', { hour12: false })}] ${message}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function reelLog(message, type = 'dim') {
  const box = document.getElementById('reelLog');
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString('en-US', { hour12: false })}] ${message}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

async function renderLogo() {
  if (!selectedFile) {
    editorLog('No file selected', 'error');
    return;
  }

  const button = document.getElementById('renderBtn');
  try {
    button.disabled = true;
    button.textContent = '⟳ RENDERING...';
    document.getElementById('progressFill').style.width = '15%';
    editorLog('Starting render...', 'info');

    const payload = {
      path: selectedFile,
      position,
      logo_size: parseInt(document.getElementById('logoSize').value, 10),
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
      ghost_size: parseInt(document.getElementById('ghostSize').value, 10),
      ghost_opacity: parseInt(document.getElementById('ghostOpac').value, 10) / 100,
      ghost_position: ghostPosition,
      ghost_fade: document.getElementById('ghostFadeToggle').checked,
      ghost_start_offset: parseFloat(document.getElementById('ghostFadeStart').value),
      ghost_fade_len: parseFloat(document.getElementById('ghostFadeLen').value),
    };

    document.getElementById('progressFill').style.width = '40%';
    const response = await fetch('/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await readJson(response);
    document.getElementById('progressFill').style.width = '100%';

    if (response.ok && result.ok) {
      editorLog(`Done: ${result.output}`, 'success');
      document.getElementById('outputPath').innerHTML = `<div class="output-path">✓ ${result.output}</div>`;
      document.getElementById('outputPreviewBox').innerHTML = `<video controls src="/video?path=${encodeURIComponent(result.output)}"></video>`;
      await refreshWorkspace().catch(error => editorLog(`Workspace refresh failed: ${error.message}`, 'warn'));
    } else {
      editorLog(`Error: ${result.error || `Render failed (${response.status})`}`, 'error');
    }
  } catch (error) {
    editorLog(`Error: ${error.message}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = '▶ RENDER VIDEO';
  }
}

function toggleCutMode() {
  const manual = document.getElementById('cutMode').value === 'manual';
  const panel = document.getElementById('manualCuts');
  panel.style.display = manual ? 'block' : 'none';
  if (manual && !document.getElementById('cutList').children.length) {
    addCut();
  }
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
    <button class="cut-remove" type="button" onclick="this.parentElement.remove()">✕</button>
  `;
  list.appendChild(row);
}

async function fetchInfo() {
  const url = document.getElementById('ytUrl').value.trim();
  if (!url) {
    reelLog('Enter a YouTube URL first', 'error');
    return;
  }

  try {
    reelLog('Fetching video info...', 'info');
    const response = await fetch('/yt_info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const info = await readJson(response);
    if (!response.ok || info.error) {
      reelLog(`Error: ${info.error || `Fetch failed (${response.status})`}`, 'error');
      return;
    }
    ytDuration = info.duration || 0;
    document.getElementById('ytPreview').innerHTML = `
      <div class="yt-thumb">
        ${info.thumbnail ? `<img src="${info.thumbnail}" alt="thumbnail">` : ''}
        <div class="yt-info">
          <div class="yt-title">${info.title || 'Unknown'}</div>
          <div class="yt-meta">${info.uploader || ''} • ${Math.floor(ytDuration / 60)}:${String(Math.floor(ytDuration % 60)).padStart(2, '0')} • ${info.view_count ? `${Number(info.view_count).toLocaleString()} views` : ''}</div>
        </div>
      </div>
    `;
    reelLog(`Found: ${info.title || url}`, 'success');
  } catch (error) {
    reelLog(`Error: ${error.message}`, 'error');
  }
}

async function startReels() {
  const url = document.getElementById('ytUrl').value.trim();
  if (!url) {
    reelLog('Enter a YouTube URL', 'error');
    return;
  }

  const button = document.getElementById('reelBtn');
  try {
    button.disabled = true;
    button.textContent = '⟳ WORKING...';
    document.getElementById('reelProgress').style.width = '5%';
    document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder padded">Processing...</div>';

    const manualCuts = [];
    if (document.getElementById('cutMode').value === 'manual') {
      const rows = document.getElementById('cutList').children;
      for (let index = 0; index < rows.length; index += 1) {
        const start = parseFloat(document.getElementById(`cut_start_${index}`)?.value);
        const end = parseFloat(document.getElementById(`cut_end_${index}`)?.value);
        if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
          manualCuts.push({ start, end });
        }
      }
    }

    const payload = {
      url,
      reel_duration: parseInt(document.getElementById('reelDuration').value, 10),
      cut_mode: document.getElementById('cutMode').value,
      manual_cuts: manualCuts,
      add_logo: document.getElementById('reelLogoToggle').checked,
      logo_position: reelPosition,
      crop_portrait: document.getElementById('reelCropToggle').checked,
      add_captions: document.getElementById('captionToggle').checked,
      caption_lang: document.getElementById('captionLang').value.trim() || 'en',
      caption_fontsize: parseInt(document.getElementById('captionSize').value, 10),
      caption_alignment: parseInt(document.getElementById('captionPos').value, 10),
      caption_box: document.getElementById('captionBox').checked,
    };

    reelLog('Downloading...', 'info');
    document.getElementById('reelProgress').style.width = '20%';

    const response = await fetch('/yt_reels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await readJson(response);
    document.getElementById('reelProgress').style.width = '100%';

    if (response.ok && result.ok) {
      const captionStatus = result.caption_status || {};
      reelLog(`Done — ${result.reels.length} reels created`, 'success');
      result.reels.forEach((path, index) => reelLog(`  Reel ${index + 1}: ${path}`, 'dim'));
      if (captionStatus.requested && !captionStatus.source_found) {
        reelLog('Auto captions were requested, but no subtitle source was found for this video.', 'warn');
      } else if (captionStatus.requested && captionStatus.source_found && !captionStatus.segments_burned) {
        reelLog('Subtitle source downloaded, but no subtitle lines landed inside the selected cuts.', 'warn');
      } else if (captionStatus.requested && captionStatus.segments_burned) {
        reelLog(`Captions burned into ${captionStatus.segments_burned} segment(s).`, 'success');
      }
      document.getElementById('reelOutput').innerHTML = `
        <div class="reel-grid">
          ${result.reels.map((path, index) => `
            <div class="reel-card">
              <video controls src="/video?path=${encodeURIComponent(path)}" loop></video>
              <div class="reel-label">Reel ${index + 1}</div>
            </div>
          `).join('')}
        </div>
      `;
      await refreshWorkspace().catch(error => reelLog(`Workspace refresh failed: ${error.message}`, 'warn'));
    } else {
      reelLog(`Error: ${result.error || `Reels failed (${response.status})`}`, 'error');
      document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder padded" style="color:var(--alert);">FAILED</div>';
    }
  } catch (error) {
    reelLog(`Error: ${error.message}`, 'error');
    document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder padded" style="color:var(--alert);">FAILED</div>';
  } finally {
    button.disabled = false;
    button.textContent = '▶ DOWNLOAD & CUT REELS';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bindTogglePanel('fadeToggle', 'fadeOptions');
  bindTogglePanel('ghostToggle', 'ghostOptions');
  bindTogglePanel('ghostFadeToggle', 'ghostFadeOptions');
  bindTogglePanel('ctaToggle', 'ctaOptions');
  bindTogglePanel('captionToggle', 'captionOptions');
  toggleCutMode();
  refreshWorkspace().catch(error => editorLog(`Workspace load failed: ${error.message}`, 'error'));
});
