let selectedFile = null;
let videoDuration = 0;
let position = 'center';
let ghostPosition = 'center';
let reelPosition = 'top-center';
let ytDuration = 0;

function readJson(response) {
  return response.json().catch(() => ({}));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return 'Unknown size';
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function readLocalJson(key, fallback) {
  try {
    if (!window.localStorage) return fallback;
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeLocalJson(key, value) {
  try {
    if (!window.localStorage) return;
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage write failures so the app still works in restricted contexts.
  }
}

const analyticsPageMap = {
  editor: { path: '/', title: 'Logo Editor' },
  reels: { path: '/youtube-reels', title: 'YouTube to Reels' },
  crop: { path: '/crop-export', title: 'Crop & Export' },
  batch: { path: '/batch-photos', title: 'Batch Photos' },
  studio: { path: '/studio', title: 'Studio' },
};

const analyticsState = {
  lastPagePath: null,
};

function analyticsEnabled() {
  return Boolean(window.REVO_GA4_MEASUREMENT_ID && typeof window.gtag === 'function');
}

function analyticsTrack(eventName, params = {}) {
  if (!analyticsEnabled()) return;
  window.gtag('event', eventName, params);
}

function analyticsTrackPageView(tabName, navigationReason = 'tab_switch') {
  const page = analyticsPageMap[tabName] || { path: `/${tabName}`, title: tabName };
  if (analyticsState.lastPagePath === page.path && navigationReason !== 'initial_load') return;
  analyticsTrack('page_view', {
    page_title: `NEXUS // ${page.title}`,
    page_path: page.path,
    page_location: `${window.location.origin}${page.path}`,
    app_section: tabName,
    navigation_reason: navigationReason,
  });
  analyticsState.lastPagePath = page.path;
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((tab, index) => {
    tab.classList.toggle('active', ['editor', 'reels', 'crop', 'batch', 'studio'][index] === name);
  });
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
  analyticsTrackPageView(name);
  if (name === 'studio') studioLoadModels().catch(() => {});
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
  updateBatchDest((data.directories || {}).batch || '~/Desktop/Nexus Exports');
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

    analyticsTrack('editor_render_start', {
      fade_enabled: payload.fade ? 1 : 0,
      cta_enabled: payload.cta ? 1 : 0,
      ghost_enabled: payload.ghost ? 1 : 0,
    });

    document.getElementById('progressFill').style.width = '40%';
    const response = await fetch('/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await readJson(response);
    document.getElementById('progressFill').style.width = '100%';

    if (response.ok && result.ok) {
      analyticsTrack('editor_render_success', {
        fade_enabled: payload.fade ? 1 : 0,
        cta_enabled: payload.cta ? 1 : 0,
        ghost_enabled: payload.ghost ? 1 : 0,
      });
      editorLog(`Done: ${result.output}`, 'success');
      document.getElementById('outputPath').innerHTML = `<div class="output-path">✓ ${result.output}</div>`;
      document.getElementById('outputPreviewBox').innerHTML = `<video controls src="/video?path=${encodeURIComponent(result.output)}"></video>`;
      await refreshWorkspace().catch(error => editorLog(`Workspace refresh failed: ${error.message}`, 'warn'));
    } else {
      analyticsTrack('editor_render_failure', {
        status_code: response.status,
      });
      editorLog(`Error: ${result.error || `Render failed (${response.status})`}`, 'error');
    }
  } catch (error) {
    analyticsTrack('editor_render_failure', {
      failure_type: 'network_or_runtime',
    });
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

    analyticsTrack('reels_job_start', {
      cut_mode: payload.cut_mode,
      reel_duration: payload.reel_duration,
      logo_enabled: payload.add_logo ? 1 : 0,
      crop_portrait: payload.crop_portrait ? 1 : 0,
      caption_enabled: payload.add_captions ? 1 : 0,
      manual_cut_count: manualCuts.length,
    });

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
      analyticsTrack('reels_job_success', {
        reels_created: (result.reels || []).length,
        caption_requested: payload.add_captions ? 1 : 0,
        captions_burned: captionStatus.segments_burned || 0,
      });
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
      analyticsTrack('reels_job_failure', {
        status_code: response.status,
      });
      reelLog(`Error: ${result.error || `Reels failed (${response.status})`}`, 'error');
      document.getElementById('reelOutput').innerHTML = '<div class="preview-placeholder padded" style="color:var(--alert);">FAILED</div>';
    }
  } catch (error) {
    analyticsTrack('reels_job_failure', {
      failure_type: 'network_or_runtime',
    });
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
  document.addEventListener('keydown', studioHandleKeydown);
  toggleCutMode();
  updateBatchDest('~/Desktop/Nexus Exports');
  studioInitialize();
  const initialTab = document.querySelector('.tab-content.active')?.id?.replace('tab-', '') || 'editor';
  analyticsTrackPageView(initialTab, 'initial_load');
  refreshWorkspace().catch(error => editorLog(`Workspace load failed: ${error.message}`, 'error'));
});

// ─── Crop & Export ───────────────────────────────────────────────────────────
let cropRatioW = 0, cropRatioH = 0;
let cropImgNaturalW = 0, cropImgNaturalH = 0;
let cropScaleX = 1, cropScaleY = 1;
let cropRect = {x:0,y:0,w:0,h:0};
let cropDragging = false, cropDragStart = {x:0,y:0};
let cropImg = null;
let cropFile = null;

function cropDragOver(e) {
  e.preventDefault();
  const zone = document.getElementById('cropDropZone');
  zone.style.borderColor = '#00f0ff';
  zone.style.background = 'linear-gradient(180deg, rgba(0,240,255,0.10), rgba(0,240,255,0.04))';
}

function cropDragLeave(e) {
  const zone = document.getElementById('cropDropZone');
  zone.style.borderColor = 'rgba(0,240,255,0.3)';
  zone.style.background = 'linear-gradient(180deg, rgba(0,240,255,0.05), rgba(0,240,255,0.02))';
}

function cropDrop(e) {
  e.preventDefault();
  cropDragLeave(e);
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) cropFileSelected(file);
}

function cropFileSelected(file) {
  if (!file) return;
  cropFile = file;
  document.getElementById('cropMeta').textContent = `${file.name} — loading...`;
  const zone = document.getElementById('cropDropZone');
  document.getElementById('cropDropPrimary').textContent = file.name;
  document.getElementById('cropDropSecondary').textContent = 'Image loaded. Drop another file here or use Choose Image to replace it.';
  zone.style.borderColor = '#00f0ff';
  zone.style.background = 'linear-gradient(180deg, rgba(0,240,255,0.10), rgba(0,240,255,0.04))';
  const reader = new FileReader();
  reader.onload = (ev) => {
    const canvas = document.getElementById('cropCanvas');
    const placeholder = document.getElementById('cropCanvasPlaceholder');
    cropImg = new Image();
    cropImg.onload = () => {
      cropImgNaturalW = cropImg.naturalWidth;
      cropImgNaturalH = cropImg.naturalHeight;
      const maxW = canvas.parentElement.clientWidth - 4;
      const scale = Math.min(1, maxW / cropImgNaturalW);
      canvas.width  = Math.round(cropImgNaturalW * scale);
      canvas.height = Math.round(cropImgNaturalH * scale);
      cropScaleX = cropImgNaturalW / canvas.width;
      cropScaleY = cropImgNaturalH / canvas.height;
      cropRect = {x:0, y:0, w:cropImgNaturalW, h:cropImgNaturalH};
      syncInputsFromCrop();
      drawCropCanvas();
      placeholder.style.display = 'none';
      canvas.style.display = 'block';
      document.getElementById('cropMeta').textContent = `${file.name} · ${cropImgNaturalW} × ${cropImgNaturalH}px`;
    };
    cropImg.onerror = () => { document.getElementById('cropMeta').textContent = 'Could not load image.'; };
    cropImg.src = ev.target.result;
    canvas.onmousedown = cropMouseDown;
    canvas.onmousemove = cropMouseMove;
    canvas.onmouseup   = cropMouseUp;
    canvas.onmouseleave = cropMouseUp;
  };
  reader.readAsDataURL(file);
}

function setRatio(w, h, el) {
  cropRatioW = w; cropRatioH = h;
  document.querySelectorAll('#tab-crop .pos-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  if (w > 0 && cropRect.w > 0) enforceRatio();
  drawCropCanvas();
}

function enforceRatio() {
  if (cropRatioW === 0) return;
  let h = Math.round(cropRect.w * cropRatioH / cropRatioW);
  h = Math.min(h, cropImgNaturalH - cropRect.y);
  cropRect.h = h;
  syncInputsFromCrop();
}

function syncInputsFromCrop() {
  document.getElementById('cropX').value = Math.round(cropRect.x);
  document.getElementById('cropY').value = Math.round(cropRect.y);
  document.getElementById('cropW').value = Math.round(cropRect.w);
  document.getElementById('cropH').value = Math.round(cropRect.h);
}

function syncCropFromInputs() {
  cropRect.x = Math.max(0, parseInt(document.getElementById('cropX').value)||0);
  cropRect.y = Math.max(0, parseInt(document.getElementById('cropY').value)||0);
  cropRect.w = Math.min(parseInt(document.getElementById('cropW').value)||0, cropImgNaturalW - cropRect.x);
  cropRect.h = Math.min(parseInt(document.getElementById('cropH').value)||0, cropImgNaturalH - cropRect.y);
  if (cropRatioW > 0 && cropRect.w > 0) enforceRatio();
  drawCropCanvas();
}


function drawCropCanvas() {
  const canvas = document.getElementById('cropCanvas');
  const ctx = canvas.getContext('2d');
  if (!cropImg) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(cropImg, 0, 0, canvas.width, canvas.height);

  // dim outside crop
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  const cx = cropRect.x / cropScaleX, cy = cropRect.y / cropScaleY;
  const cw = cropRect.w / cropScaleX, ch = cropRect.h / cropScaleY;
  ctx.fillRect(0, 0, canvas.width, cy);
  ctx.fillRect(0, cy + ch, canvas.width, canvas.height - cy - ch);
  ctx.fillRect(0, cy, cx, ch);
  ctx.fillRect(cx + cw, cy, canvas.width - cx - cw, ch);

  // crop border
  ctx.strokeStyle = '#00f0ff';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(cx, cy, cw, ch);

  // rule-of-thirds grid
  ctx.strokeStyle = 'rgba(0,240,255,0.25)';
  ctx.lineWidth = 0.5;
  for (let i = 1; i < 3; i++) {
    ctx.beginPath(); ctx.moveTo(cx + cw*i/3, cy); ctx.lineTo(cx + cw*i/3, cy+ch); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy + ch*i/3); ctx.lineTo(cx+cw, cy + ch*i/3); ctx.stroke();
  }

  // size label
  ctx.fillStyle = '#00f0ff';
  ctx.font = '11px JetBrains Mono, monospace';
  ctx.fillText(`${Math.round(cropRect.w)} × ${Math.round(cropRect.h)}`, cx + 6, cy + 16);
}

function cropMouseDown(e) {
  const r = e.target.getBoundingClientRect();
  const mx = (e.clientX - r.left) * cropScaleX;
  const my = (e.clientY - r.top)  * cropScaleY;
  cropDragging = true;
  cropDragStart = {x: mx, y: my};
  cropRect = {x: mx, y: my, w: 0, h: 0};
}

function cropMouseMove(e) {
  if (!cropDragging) return;
  const r = e.target.getBoundingClientRect();
  let mx = Math.min(Math.max(0, (e.clientX - r.left) * cropScaleX), cropImgNaturalW);
  let my = Math.min(Math.max(0, (e.clientY - r.top)  * cropScaleY), cropImgNaturalH);
  cropRect.x = Math.min(cropDragStart.x, mx);
  cropRect.y = Math.min(cropDragStart.y, my);
  cropRect.w = Math.abs(mx - cropDragStart.x);
  cropRect.h = Math.abs(my - cropDragStart.y);
  if (cropRatioW > 0 && cropRect.w > 0) {
    cropRect.h = Math.min(cropRect.w * cropRatioH / cropRatioW, cropImgNaturalH - cropRect.y);
  }
  syncInputsFromCrop();
  drawCropCanvas();
}

function cropMouseUp() { cropDragging = false; }

async function runCrop() {
  if (!cropFile || cropRect.w < 1 || cropRect.h < 1) return;
  const btn = document.getElementById('cropBtn');
  btn.disabled = true; btn.textContent = '⟳ EXPORTING...';

  const form = new FormData();
  form.append('file', cropFile);
  form.append('x', Math.round(cropRect.x));
  form.append('y', Math.round(cropRect.y));
  form.append('w', Math.round(cropRect.w));
  form.append('h', Math.round(cropRect.h));
  form.append('quality', parseInt(document.getElementById('cropQual').value));

  const r = await fetch('/crop_upload', {method:'POST', body:form});
  const result = await r.json();
  if (result.ok) {
    document.getElementById('cropOutputPath').innerHTML =
      `<div class="output-path">✓ ${result.output}${result.format ? ` <span style="opacity:0.7;">(${result.format})</span>` : ''}</div>`;
    document.getElementById('cropPreviewBox').innerHTML =
      `<img src="/img_preview?path=${encodeURIComponent(result.output)}" style="max-width:100%;max-height:400px;display:block;border-radius:4px;">`;
  } else {
    document.getElementById('cropOutputPath').innerHTML =
      `<div class="output-path" style="border-color:var(--alert);color:var(--alert);">✕ ${result.error}</div>`;
  }
  btn.disabled = false; btn.textContent = '⬚ EXPORT CROP';
}

async function runCompress() {
  if (!cropFile) {
    document.getElementById('compressSizeNote').textContent = 'Drop an image first.';
    return;
  }
  const btn = document.getElementById('compressBtn');
  btn.disabled = true; btn.textContent = '⟳ COMPRESSING...';
  document.getElementById('compressOutputPath').innerHTML = '';

  const form = new FormData();
  form.append('file', cropFile);
  form.append('format', document.getElementById('compressFormat').value);
  form.append('quality', parseInt(document.getElementById('compressQual').value));

  const r = await fetch('/compress_upload', {method:'POST', body:form});
  const result = await r.json();
  if (result.ok) {
    document.getElementById('compressSizeNote').textContent =
      `${result.original_size} → ${result.output_size}  (${result.savings} smaller)`;
    document.getElementById('compressOutputPath').innerHTML =
      `<div class="output-path">✓ ${result.output}${result.format ? ` <span style="opacity:0.7;">(${result.format})</span>` : ''}</div>`;
    document.getElementById('cropPreviewBox').innerHTML =
      `<img src="/img_preview?path=${encodeURIComponent(result.output)}" style="max-width:100%;max-height:400px;display:block;border-radius:4px;">`;
  } else {
    document.getElementById('compressOutputPath').innerHTML =
      `<div class="output-path" style="border-color:var(--alert);color:var(--alert);">✕ ${result.error}</div>`;
  }
  btn.disabled = false; btn.textContent = '◈ COMPRESS IMAGE';
}

// ─── BATCH PHOTOS ──────────────────────────────────────────────────────────

let batchFiles = [];
let batchMode = 'center_ratio'; // 'center_ratio' | 'manual'
let batchRatioW = 1;
let batchRatioH = 1;
let batchRefNaturalW = 0;
let batchRefNaturalH = 0;

function prettyPath(path) {
  if (!path) return '';
  return path.replace(/^\/Users\/[^/]+/, '~');
}

function updateBatchDest(path) {
  const note = document.getElementById('batchDestNote');
  if (!note) return;
  const label = prettyPath(path) || '~/Desktop/Nexus Exports';
  note.innerHTML = `Output: <span style="color:var(--accent);">${label}</span>`;
}

function clearBatchReference() {
  batchRefNaturalW = 0;
  batchRefNaturalH = 0;
  document.getElementById('batchX').value = 0;
  document.getElementById('batchY').value = 0;
  document.getElementById('batchW').value = 0;
  document.getElementById('batchH').value = 0;
  document.getElementById('batchRefDims').textContent = '';
}

function loadBatchReference(file, forceSelection = false) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = new Image();
    img.onload = () => {
      batchRefNaturalW = img.naturalWidth;
      batchRefNaturalH = img.naturalHeight;
      document.getElementById('batchRefDims').textContent =
        `Reference: ${img.naturalWidth} × ${img.naturalHeight}px`;
      if (forceSelection) {
        document.getElementById('batchX').value = 0;
        document.getElementById('batchY').value = 0;
        document.getElementById('batchW').value = img.naturalWidth;
        document.getElementById('batchH').value = img.naturalHeight;
      }
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

function batchDragOver(e) {
  e.preventDefault();
  const zone = document.getElementById('batchDropZone');
  zone.style.borderColor = '#00f0ff';
  zone.style.background = 'linear-gradient(180deg, rgba(0,240,255,0.10), rgba(0,240,255,0.04))';
}

function batchDragLeave(e) {
  const zone = document.getElementById('batchDropZone');
  zone.style.borderColor = 'rgba(0,240,255,0.3)';
  zone.style.background = 'linear-gradient(180deg, rgba(0,240,255,0.05), rgba(0,240,255,0.02))';
}

function batchDrop(e) {
  e.preventDefault();
  batchDragLeave(e);
  const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
  if (files.length) batchAddFiles(files);
}

function batchFilesSelected(fileList) {
  const files = Array.from(fileList).filter(f => f.type.startsWith('image/'));
  if (files.length) batchAddFiles(files);
  document.getElementById('batchFileInput').value = '';
}

function batchAddFiles(files) {
  const wasEmpty = batchFiles.length === 0;
  batchFiles.push(...files);
  renderBatchQueue();
  if (wasEmpty && batchFiles[0]) {
    loadBatchReference(batchFiles[0], true);
  }
}

function batchClearQueue() {
  batchFiles = [];
  clearBatchReference();
  renderBatchQueue();
  document.getElementById('batchLog').innerHTML = '<div class="log-line dim">// Queue cleared</div>';
  document.getElementById('batchProgress').style.width = '0%';
  document.getElementById('batchResults').innerHTML = '<div class="preview-placeholder padded">Results will appear here</div>';
}

function renderBatchQueue() {
  const el = document.getElementById('batchQueue');
  if (!batchFiles.length) {
    el.innerHTML = '';
    return;
  }
  el.innerHTML = `
    <div style="font-size:0.7rem;color:var(--text-dim);margin-bottom:0.5rem;">${batchFiles.length} file${batchFiles.length !== 1 ? 's' : ''} queued</div>
    <div style="max-height:180px;overflow-y:auto;display:flex;flex-direction:column;gap:0.3rem;">
      ${batchFiles.map((f, i) => `
        <div class="recent-item" style="padding:0.4rem 0.7rem;">
          <div class="recent-meta">
            <div class="recent-name">${f.name}</div>
            <div class="recent-sub">${(f.size / 1024).toFixed(0)} KB</div>
          </div>
          <button class="cut-remove" onclick="batchRemoveFile(${i})">✕</button>
        </div>
      `).join('')}
    </div>`;
}

function batchRemoveFile(i) {
  batchFiles.splice(i, 1);
  if (!batchFiles.length) {
    clearBatchReference();
  } else if (i === 0) {
    loadBatchReference(batchFiles[0], true);
  }
  renderBatchQueue();
}

function setBatchMode(mode, el) {
  batchMode = mode;
  document.querySelectorAll('#batchModeCenterRatio, #batchModeManual').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('batchCenterRatioSettings').style.display = mode === 'center_ratio' ? '' : 'none';
  document.getElementById('batchManualSettings').style.display = mode === 'manual' ? '' : 'none';
  if (mode === 'manual') {
    if (batchFiles.length) {
      const shouldResetSelection = !(batchRefNaturalW > 0 && batchRefNaturalH > 0);
      loadBatchReference(batchFiles[0], shouldResetSelection);
    } else {
      clearBatchReference();
    }
  }
}

function setBatchRatio(w, h, el) {
  batchRatioW = w;
  batchRatioH = h;
  document.querySelectorAll('[id^="batchRatio_"]').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function batchLog(msg, cls = '') {
  const box = document.getElementById('batchLog');
  const line = document.createElement('div');
  line.className = `log-line ${cls}`;
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

async function runBatch(op) {
  if (!batchFiles.length) {
    batchLog('// No files queued — drop some images first', 'warn');
    return;
  }
  const btn = document.getElementById(op === 'crop' ? 'batchRunCropBtn' : 'batchRunCompressBtn');
  btn.disabled = true;
  btn.textContent = '⟳ RUNNING...';
  document.getElementById('batchLog').innerHTML = '';
  document.getElementById('batchProgress').style.width = '0%';
  document.getElementById('batchResults').innerHTML = '';

  batchLog(`// Starting ${op} on ${batchFiles.length} file(s)...`, 'info');
  analyticsTrack('batch_job_start', {
    operation: op,
    file_count: batchFiles.length,
    mode: op === 'crop' ? batchMode : 'compress',
  });

  const form = new FormData();
  batchFiles.forEach(f => form.append('files[]', f));

  let url;
  if (op === 'crop') {
    url = '/batch_crop_upload';
    form.append('mode', batchMode);
    form.append('ratio_w', batchRatioW);
    form.append('ratio_h', batchRatioH);
    form.append('quality', parseInt(document.getElementById('batchCropQual').value));
    if (batchMode === 'manual') {
      form.append('x', parseInt(document.getElementById('batchX').value) || 0);
      form.append('y', parseInt(document.getElementById('batchY').value) || 0);
      form.append('w', parseInt(document.getElementById('batchW').value) || 1);
      form.append('h', parseInt(document.getElementById('batchH').value) || 1);
      form.append('proportional', document.getElementById('batchProportional').checked ? 'true' : 'false');
      form.append('ref_w', batchRefNaturalW || parseInt(document.getElementById('batchW').value) || 1);
      form.append('ref_h', batchRefNaturalH || parseInt(document.getElementById('batchH').value) || 1);
    }
  } else {
    url = '/batch_compress_upload';
    form.append('format', document.getElementById('batchCompressFormat').value);
    form.append('quality', parseInt(document.getElementById('batchCompressQual').value));
  }
  const opLabel = op === 'crop' ? '⬚ RUN BATCH CROP' : '◈ RUN BATCH COMPRESS';

  try {
    const r = await fetch(url, { method: 'POST', body: form });
    const data = await r.json();

    if (!data.ok) {
      analyticsTrack('batch_job_failure', {
        operation: op,
        status_code: r.status,
      });
      batchLog(`✕ ${data.error}`, 'error');
      btn.disabled = false; btn.textContent = opLabel;
      return;
    }

    const results = data.results || [];
    let ok = 0, fail = 0;
    const resultRows = [];

    results.forEach((res, i) => {
      const pct = Math.round(((i + 1) / results.length) * 100);
      document.getElementById('batchProgress').style.width = `${pct}%`;
      if (res.ok) {
        ok++;
        const detail = res.savings
          ? `${res.original_size} → ${res.output_size} (${res.savings} smaller)`
          : res.size || '';
        batchLog(`✓ ${res.name}  ${detail}`, 'success');
        resultRows.push(`<div class="recent-item"><div class="recent-meta"><div class="recent-name">${res.name}</div><div class="recent-sub">${detail}</div></div><span class="status-pill ok">✓</span></div>`);
      } else {
        fail++;
        batchLog(`✕ ${res.name}: ${res.error}`, 'error');
        resultRows.push(`<div class="recent-item"><div class="recent-meta"><div class="recent-name">${res.name}</div><div class="recent-sub" style="color:var(--alert);">${res.error}</div></div><span class="status-pill danger">✕</span></div>`);
      }
    });

    batchLog(`// Done — ${ok} exported, ${fail} failed`, ok > 0 ? 'info' : 'warn');
    analyticsTrack('batch_job_success', {
      operation: op,
      file_count: batchFiles.length,
      ok_count: ok,
      fail_count: fail,
    });
    if (data.dest) {
      batchLog(`// Output: ${data.dest}`, 'dim');
      updateBatchDest(data.dest);
    }

    document.getElementById('batchResults').innerHTML =
      `<div style="font-size:0.72rem;color:var(--text-dim);margin-bottom:0.75rem;">${ok}/${results.length} exported → <span style="color:var(--accent);">${prettyPath(data.dest)}</span></div>` +
      `<div style="display:flex;flex-direction:column;gap:0.35rem;">${resultRows.join('')}</div>`;

  } catch (err) {
    analyticsTrack('batch_job_failure', {
      operation: op,
      failure_type: 'network_or_runtime',
    });
    batchLog(`✕ Request failed: ${err.message}`, 'error');
  }

  btn.disabled = false; btn.textContent = opLabel;
}

// ─── STUDIO ────────────────────────────────────────────────────────────────

let studioFile = null;
const STUDIO_BRIEF_STORAGE_KEY = 'revo_studio_brief_v1';
const STUDIO_HISTORY_STORAGE_KEY = 'revo_studio_history_v1';
const STUDIO_PRESET_STORAGE_KEY = 'revo_studio_presets_v1';
const STUDIO_UI_STORAGE_KEY = 'revo_studio_ui_v1';
const studioDefaults = {
  bg: 'warm white',
  frame: 'three-quarter crop',
  energy: 'still editorial',
  use_case: 'pdp hero image',
  aspect_ratio: 'original proportion',
};
const studioLabels = {
  'warm white': 'Warm White',
  cream: 'Cream',
  sand: 'Sand',
  'warm grey': 'Warm Grey',
  taupe: 'Taupe',
  blush: 'Blush',
  sage: 'Sage',
  stone: 'Stone',
  'full length': 'Full Length',
  'three-quarter crop': 'Three-Quarter',
  'waist-up focus': 'Waist Up',
  'still editorial': 'Still Editorial',
  'soft movement': 'Soft Movement',
  'campaign confidence': 'Campaign',
  'pdp hero image': 'PDP Hero',
  'lookbook story': 'Lookbook',
  'paid social creative': 'Paid Social',
  'original proportion': 'Original',
  '1:1 square': '1:1',
  '4:5 portrait': '4:5',
  '9:16 vertical': '9:16',
};
let studioBg = studioDefaults.bg;
let studioDirection = {
  frame: studioDefaults.frame,
  energy: studioDefaults.energy,
  use_case: studioDefaults.use_case,
  aspect_ratio: studioDefaults.aspect_ratio,
};
let studioResultPath = null;
let studioHistory = [];
let studioPresets = [];
let studioSelectedHistoryPath = null;
let studioReferenceSrc = null;
let studioVariantCount = 1;
let studioCurrentRun = [];
let studioCompareSplit = 50;
let studioCompareMode = 'slider';
let studioIsRunning = false;
let studioRunAbortRequested = false;
let studioRunController = null;
let studioHistoryFilter = 'all';
let studioSuggestedAspectRatio = null;
let studioSourceOriginalFile = null;
let studioSourceOriginalReferenceSrc = null;
let studioSourceRotation = 0;
let studioSourceCropAspect = null;
let studioModels = [];
let studioSelectedModelId = null;
let studioPresetStyleChoice = 'boho';
let studioRefFileData = null;

function studioLabel(value) {
  return studioLabels[value] || value;
}

function studioApplyStateToUi() {
  document.querySelectorAll('.studio-swatch').forEach(swatch => {
    swatch.classList.toggle('active', swatch.dataset.bg === studioBg);
  });
  document.querySelectorAll('.studio-choice').forEach(choice => {
    choice.classList.toggle('active', studioDirection[choice.dataset.group] === choice.dataset.value);
  });
}

function studioPersistState() {
  writeLocalJson(STUDIO_BRIEF_STORAGE_KEY, studioCurrentBriefPayload());
}

function studioPersistUiState() {
  writeLocalJson(STUDIO_UI_STORAGE_KEY, {
    variantCount: studioVariantCount,
    compareMode: studioCompareMode,
    historyFilter: studioHistoryFilter,
  });
}

function studioRestoreState() {
  const stored = readLocalJson(STUDIO_BRIEF_STORAGE_KEY, {});
  studioApplyBrief(stored);
}

function studioRestoreUiState() {
  const stored = readLocalJson(STUDIO_UI_STORAGE_KEY, {});
  studioVariantCount = [1, 2, 4].includes(stored.variantCount) ? stored.variantCount : 1;
  studioCompareMode = ['slider', 'focus'].includes(stored.compareMode) ? stored.compareMode : 'slider';
  studioHistoryFilter = ['all', 'favorites', 'shortlisted', 'approved'].includes(stored.historyFilter) ? stored.historyFilter : 'all';
}

function studioSetPill(id, tone, label) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `status-pill ${tone}`;
  el.textContent = label;
}

function studioSetBoxPlaceholder(id, label) {
  const box = document.getElementById(id);
  if (!box) return;
  box.innerHTML = `<span class="preview-placeholder">${escapeHtml(label)}</span>`;
}

function studioRenderImage(id, src, alt) {
  const box = document.getElementById(id);
  if (!box) return;
  box.innerHTML = `<img src="${src}" alt="${escapeHtml(alt)}">`;
}

function studioSetDropActive(active) {
  const zone = document.getElementById('studioDropZone');
  if (!zone) return;
  zone.classList.toggle('is-active', active);
}

function studioSyncSourceActions() {
  const clearBtn = document.getElementById('studioClearSourceBtn');
  const rotateLeftBtn = document.getElementById('studioRotateLeftBtn');
  const rotateRightBtn = document.getElementById('studioRotateRightBtn');
  const resetOrientationBtn = document.getElementById('studioResetOrientationBtn');
  const cropSquareBtn = document.getElementById('studioCropSquareBtn');
  const cropPortraitBtn = document.getElementById('studioCropPortraitBtn');
  const cropVerticalBtn = document.getElementById('studioCropVerticalBtn');
  const resetCropBtn = document.getElementById('studioResetCropBtn');
  const hasSource = Boolean(studioFile);
  if (clearBtn) {
    clearBtn.style.display = hasSource ? '' : 'none';
    clearBtn.disabled = studioIsRunning;
  }
  if (rotateLeftBtn) {
    rotateLeftBtn.style.display = hasSource ? '' : 'none';
    rotateLeftBtn.disabled = studioIsRunning;
  }
  if (rotateRightBtn) {
    rotateRightBtn.style.display = hasSource ? '' : 'none';
    rotateRightBtn.disabled = studioIsRunning;
  }
  if (resetOrientationBtn) {
    resetOrientationBtn.style.display = hasSource && studioSourceRotation !== 0 ? '' : 'none';
    resetOrientationBtn.disabled = studioIsRunning;
  }
  if (cropSquareBtn) {
    cropSquareBtn.style.display = hasSource ? '' : 'none';
    cropSquareBtn.disabled = studioIsRunning || studioSourceCropAspect === '1:1';
  }
  if (cropPortraitBtn) {
    cropPortraitBtn.style.display = hasSource ? '' : 'none';
    cropPortraitBtn.disabled = studioIsRunning || studioSourceCropAspect === '4:5';
  }
  if (cropVerticalBtn) {
    cropVerticalBtn.style.display = hasSource ? '' : 'none';
    cropVerticalBtn.disabled = studioIsRunning || studioSourceCropAspect === '9:16';
  }
  if (resetCropBtn) {
    resetCropBtn.style.display = hasSource && studioSourceCropAspect ? '' : 'none';
    resetCropBtn.disabled = studioIsRunning;
  }
}

function studioFormatSourceMeta(file) {
  if (!file) {
    return 'Reference not loaded yet. Once a file is selected, we will build a reusable studio brief around it.';
  }
  const transformLabel = studioFormatSourceTransform(studioSourceRotation, studioSourceCropAspect);
  return `${file.name} · ${formatFileSize(file.size)} · ${file.type || 'image file'}${transformLabel ? ` · ${transformLabel}` : ''}`;
}

function studioSetSourceMeta(file) {
  const meta = document.getElementById('studioSourceMeta');
  if (!meta) return;
  meta.textContent = studioFormatSourceMeta(file);
}

function studioFormatSourceRotation(rotation) {
  return rotation === 0 ? 'Original orientation' : `Rotated ${rotation}\u00B0`;
}

function studioFormatSourceCrop(cropAspect) {
  if (!cropAspect) return 'Original frame';
  return `Cropped ${cropAspect}`;
}

function studioFormatSourceTransform(rotation, cropAspect) {
  const parts = [];
  if (rotation !== 0) parts.push(studioFormatSourceRotation(rotation));
  if (cropAspect) parts.push(studioFormatSourceCrop(cropAspect));
  return parts.join(' · ');
}

function studioBuildHistorySourceLabel(item) {
  const sourceName = item?.sourceName || null;
  const sourceRotation = Number.isFinite(item?.sourceRotation) ? item.sourceRotation : 0;
  const sourceCropAspect = item?.sourceCropAspect || null;
  if (!sourceName) return '';
  const transformLabel = studioFormatSourceTransform(sourceRotation, sourceCropAspect) || 'Original orientation';
  return `${sourceName} · ${transformLabel}`;
}

function studioCurrentSourceDescriptor() {
  const sourceName = studioSourceOriginalFile?.name || null;
  if (!sourceName) return null;
  return {
    sourceName,
    sourceRotation: studioSourceRotation,
    sourceCropAspect: studioSourceCropAspect,
  };
}

function studioSelectedResultItem() {
  if (!studioResultPath) return null;
  return studioHistory.find(item => item.path === studioResultPath)
    || studioCurrentRun.find(item => item.path === studioResultPath)
    || null;
}

function studioReviewStatusLabel(status) {
  return status === 'approved'
    ? 'Approved'
    : status === 'shortlisted'
      ? 'Shortlisted'
      : '';
}

function studioReviewPriority(item) {
  return item?.reviewStatus === 'approved'
    ? 2
    : item?.reviewStatus === 'shortlisted'
      ? 1
      : 0;
}

function studioCompareAvailability() {
  if (!studioReferenceSrc) {
    return {
      enabled: false,
      message: 'Load a source image to unlock the compare reveal slider for this result.',
    };
  }

  const selectedItem = studioSelectedResultItem();
  if (!selectedItem) {
    return { enabled: true, message: '' };
  }

  if (!selectedItem.sourceName) {
    return {
      enabled: false,
      message: 'Compare is disabled for this older saved shot because it does not include source tracking metadata.',
    };
  }

  const currentSource = studioCurrentSourceDescriptor();
  if (!currentSource) {
    return {
      enabled: false,
      message: 'Load the matching source image to compare this Studio shot accurately.',
    };
  }

  if (
    currentSource.sourceName !== selectedItem.sourceName
    || currentSource.sourceRotation !== (selectedItem.sourceRotation || 0)
    || (currentSource.sourceCropAspect || null) !== (selectedItem.sourceCropAspect || null)
  ) {
    return {
      enabled: false,
      message: `Compare is locked to avoid a mismatch. This shot was generated from ${studioBuildHistorySourceLabel(selectedItem)}.`,
    };
  }

  return { enabled: true, message: '' };
}

function studioDecodeImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Failed to decode source image.'));
    img.src = src;
  });
}

function studioBuildTransformedFileName(file, type, rotation, cropAspect) {
  const name = file?.name || 'studio-source';
  const dotIndex = name.lastIndexOf('.');
  const base = dotIndex > 0 ? name.slice(0, dotIndex) : name;
  const extensionMap = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
  };
  const extension = extensionMap[type] || (dotIndex > 0 ? name.slice(dotIndex + 1) : 'png');
  const rotationSuffix = rotation === 0 ? '' : `-rotated-${rotation}`;
  const cropSuffix = cropAspect ? `-crop-${cropAspect.replace(':', 'x')}` : '';
  return `${base}${rotationSuffix}${cropSuffix}.${extension}`;
}

function studioBuildCropBounds(width, height, cropAspect) {
  if (!cropAspect) {
    return { x: 0, y: 0, width, height };
  }
  const [aspectWidth, aspectHeight] = cropAspect.split(':').map(Number);
  const targetRatio = aspectWidth / aspectHeight;
  const currentRatio = width / height;
  if (!Number.isFinite(targetRatio) || !targetRatio) {
    return { x: 0, y: 0, width, height };
  }

  let cropWidth = width;
  let cropHeight = height;
  let cropX = 0;
  let cropY = 0;

  if (currentRatio > targetRatio) {
    cropWidth = Math.round(height * targetRatio);
    cropX = Math.max(0, Math.round((width - cropWidth) / 2));
  } else if (currentRatio < targetRatio) {
    cropHeight = Math.round(width / targetRatio);
    cropY = Math.max(0, Math.round((height - cropHeight) / 2));
  }

  return {
    x: cropX,
    y: cropY,
    width: Math.max(1, cropWidth),
    height: Math.max(1, cropHeight),
  };
}

async function studioBuildTransformedSource(rotation, cropAspect) {
  if (!studioSourceOriginalFile || !studioSourceOriginalReferenceSrc) {
    throw new Error('Original Studio source is unavailable.');
  }

  if (rotation === 0 && !cropAspect) {
    return {
      file: studioSourceOriginalFile,
      referenceSrc: studioSourceOriginalReferenceSrc,
    };
  }

  const image = await studioDecodeImage(studioSourceOriginalReferenceSrc);
  const rotatedCanvas = document.createElement('canvas');
  const quarterTurns = Math.round(rotation / 90) % 4;
  const swapSides = quarterTurns % 2 === 1;
  rotatedCanvas.width = swapSides ? image.naturalHeight : image.naturalWidth;
  rotatedCanvas.height = swapSides ? image.naturalWidth : image.naturalHeight;
  const rotatedContext = rotatedCanvas.getContext('2d');
  if (!rotatedContext) throw new Error('Canvas rendering is unavailable.');

  rotatedContext.translate(rotatedCanvas.width / 2, rotatedCanvas.height / 2);
  rotatedContext.rotate((rotation * Math.PI) / 180);
  rotatedContext.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);

  const cropBounds = studioBuildCropBounds(rotatedCanvas.width, rotatedCanvas.height, cropAspect);
  const finalCanvas = document.createElement('canvas');
  finalCanvas.width = cropBounds.width;
  finalCanvas.height = cropBounds.height;
  const finalContext = finalCanvas.getContext('2d');
  if (!finalContext) throw new Error('Canvas rendering is unavailable.');

  finalContext.drawImage(
    rotatedCanvas,
    cropBounds.x,
    cropBounds.y,
    cropBounds.width,
    cropBounds.height,
    0,
    0,
    cropBounds.width,
    cropBounds.height,
  );

  const outputType = ['image/jpeg', 'image/png', 'image/webp'].includes(studioSourceOriginalFile.type)
    ? studioSourceOriginalFile.type
    : 'image/png';
  const blob = await new Promise((resolve, reject) => {
    finalCanvas.toBlob(result => {
      if (result) {
        resolve(result);
      } else {
        reject(new Error('Failed to build transformed source image.'));
      }
    }, outputType, 0.96);
  });

  return {
    file: new File([blob], studioBuildTransformedFileName(studioSourceOriginalFile, outputType, rotation, cropAspect), {
      type: outputType,
      lastModified: Date.now(),
    }),
    referenceSrc: finalCanvas.toDataURL(outputType, 0.96),
  };
}

async function studioApplySourceTransform(rotation, cropAspect, statusMessage) {
  studioSetPill('studioSourceStatus', 'warn', 'Updating');
  studioResetSourceDiagnostics(statusMessage);
  const transformed = await studioBuildTransformedSource(rotation, cropAspect);
  studioSourceRotation = rotation;
  studioSourceCropAspect = cropAspect;
  studioApplySourceState(transformed.file, transformed.referenceSrc);
}

function studioApplySourceState(file, referenceSrc, { resetRotation = false } = {}) {
  studioFile = file;
  studioReferenceSrc = referenceSrc;
  if (resetRotation) {
    studioSourceRotation = 0;
    studioSourceCropAspect = null;
  }
  studioSetDropActive(Boolean(file));
  studioSyncSourceActions();
  studioSetPill('studioSourceStatus', 'warn', 'Analyzing');
  document.getElementById('studioDropPrimary').textContent = file.name;
  document.getElementById('studioDropSecondary').textContent = 'Reference loaded. Tune the brief, then generate a polished studio render.';
  studioSetSourceMeta(file);
  studioResetSourceDiagnostics('Analyzing the source photo for Studio readiness...');
  studioResetResult();

  const img = document.getElementById('studioSourceImg');
  img.onload = () => {
    studioRenderSourceDiagnostics(file, img.naturalWidth, img.naturalHeight);
  };
  img.onerror = () => {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    studioResetSourceDiagnostics('We loaded the file, but could not inspect its dimensions. Try another image or re-export this one.');
  };
  img.src = referenceSrc;
  document.getElementById('studioSourcePreview').style.display = 'block';
  studioRenderImage('studioReferenceBox', referenceSrc, 'Studio reference');
  studioRenderResultFrame();
  document.getElementById('studioGenBtn').disabled = false;
  studioRefreshVariantRunSummary();
  studioRefreshBrief();
}

async function studioRotateSource(delta) {
  if (!studioSourceOriginalFile || !studioSourceOriginalReferenceSrc) return;
  if (studioIsRunning) {
    studioLog('Stop the current Studio run before rotating the source photo.', 'warn');
    return;
  }
  if (!studioConfirmRunReplacement()) return;

  const nextRotation = ((studioSourceRotation + delta) % 360 + 360) % 360;
  const actionLabel = nextRotation === 0
    ? studioSourceCropAspect
      ? 'Restored the original source orientation while keeping the active crop.'
      : 'Reset source orientation to the original upload.'
    : `Rotated source photo to ${nextRotation}\u00B0.`;
  try {
    await studioApplySourceTransform(nextRotation, studioSourceCropAspect, 'Applying rotation to the source photo...');
    studioLog(actionLabel, nextRotation === 0 ? 'dim' : 'info');
  } catch (error) {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    studioResetSourceDiagnostics('Rotation failed for this file. Try another export of the source image.');
    studioLog(error.message || 'Unable to rotate the source image.', 'error');
  }
}

async function studioCropSource(cropAspect) {
  if (!studioSourceOriginalFile || !studioSourceOriginalReferenceSrc) return;
  if (studioIsRunning) {
    studioLog('Stop the current Studio run before cropping the source photo.', 'warn');
    return;
  }
  if (studioSourceCropAspect === cropAspect) {
    studioLog(`Source crop ${cropAspect} is already active.`, 'dim');
    return;
  }
  try {
    if (!studioConfirmRunReplacement()) return;
    await studioApplySourceTransform(studioSourceRotation, cropAspect, `Applying a centered ${cropAspect} crop to the source photo...`);
    studioLog(`Applied ${cropAspect} crop to the source photo.`, 'info');
  } catch (error) {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    studioResetSourceDiagnostics('Cropping failed for this file. Try another export of the source image.');
    studioLog(error.message || 'Unable to crop the source image.', 'error');
  }
}

async function studioResetOrientation() {
  if (!studioSourceOriginalFile || !studioSourceOriginalReferenceSrc || studioSourceRotation === 0) return;
  if (studioIsRunning) {
    studioLog('Stop the current Studio run before resetting the source orientation.', 'warn');
    return;
  }
  if (!studioConfirmRunReplacement()) return;
  try {
    await studioApplySourceTransform(0, studioSourceCropAspect, 'Restoring the original source orientation...');
    studioLog(
      studioSourceCropAspect
        ? 'Restored the original source orientation while keeping the active crop.'
        : 'Reset source orientation to the original upload.',
      'dim',
    );
  } catch (error) {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    studioResetSourceDiagnostics('Orientation reset failed for this file. Try another export of the source image.');
    studioLog(error.message || 'Unable to reset the source orientation.', 'error');
  }
}

async function studioResetSourceCrop() {
  if (!studioSourceOriginalFile || !studioSourceOriginalReferenceSrc || !studioSourceCropAspect) return;
  if (studioIsRunning) {
    studioLog('Stop the current Studio run before resetting the source crop.', 'warn');
    return;
  }
  if (!studioConfirmRunReplacement()) return;
  try {
    await studioApplySourceTransform(studioSourceRotation, null, 'Restoring the original source framing...');
    studioLog('Restored the original source framing.', 'dim');
  } catch (error) {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    studioResetSourceDiagnostics('Crop reset failed for this file. Try another export of the source image.');
    studioLog(error.message || 'Unable to reset the source crop.', 'error');
  }
}

function studioRefreshSourceSuggestion() {
  const box = document.getElementById('studioSourceSuggestion');
  const copy = document.getElementById('studioSourceSuggestionText');
  const button = document.getElementById('studioSourceSuggestionBtn');
  if (!box || !copy || !button) return;

  if (!studioFile || !studioSuggestedAspectRatio) {
    box.style.display = 'none';
    copy.textContent = '';
    button.disabled = false;
    button.textContent = 'Use Suggested Ratio';
    return;
  }

  const isApplied = studioDirection.aspect_ratio === studioSuggestedAspectRatio;
  box.style.display = '';
  copy.textContent = isApplied
    ? `Suggested output ratio is already active: ${studioLabel(studioSuggestedAspectRatio)}.`
    : `Suggested output ratio for this source: ${studioLabel(studioSuggestedAspectRatio)}.`;
  button.disabled = isApplied;
  button.textContent = isApplied ? 'Applied' : `Use ${studioLabel(studioSuggestedAspectRatio)}`;
}

function studioResetSourceDiagnostics(message = 'Upload a product photo to see image-readiness guidance for the generator.') {
  const badges = document.getElementById('studioSourceBadges');
  const warnings = document.getElementById('studioSourceWarnings');
  studioSuggestedAspectRatio = null;
  studioRefreshSourceSuggestion();
  if (badges) {
    badges.innerHTML = '<span class="studio-chip">Waiting for source</span>';
  }
  if (warnings) {
    warnings.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  }
}

function studioRenderSourceDiagnostics(file, width, height) {
  const badges = document.getElementById('studioSourceBadges');
  const warnings = document.getElementById('studioSourceWarnings');
  const safeWidth = Math.max(0, Number(width) || 0);
  const safeHeight = Math.max(0, Number(height) || 0);
  if (!badges || !warnings) return;

  if (!safeWidth || !safeHeight) {
    studioSetPill('studioSourceStatus', 'warn', 'Review Source');
    badges.innerHTML = [
      'Review Source',
      file?.type ? file.type.replace('image/', '').toUpperCase() : 'IMAGE',
      formatFileSize(file?.size || 0),
    ].map(item => `<span class="studio-chip">${escapeHtml(item)}</span>`).join('');
    warnings.innerHTML = '<div class="studio-source-warning warn">We loaded the preview, but could not read the image dimensions. Try a fresh export of the original photo.</div>';
    return;
  }

  const longestEdge = Math.max(safeWidth, safeHeight);
  const shortestEdge = Math.min(safeWidth, safeHeight);
  const aspectRatio = safeWidth / safeHeight;
  const megapixels = (safeWidth * safeHeight) / 1000000;
  const orientation = Math.abs(aspectRatio - 1) < 0.08
    ? 'Square'
    : aspectRatio > 1
      ? 'Landscape'
      : 'Portrait';
  const guidance = [];
  const cautions = [];

  if (longestEdge < 1200 || shortestEdge < 900) {
    cautions.push('Small source; use a sharper original if possible.');
  } else if (longestEdge >= 1800 && shortestEdge >= 1200) {
    guidance.push('High-res source gives the generator more garment detail.');
  } else {
    guidance.push('Resolution is solid for a clean Studio generation pass.');
  }

  if ((file?.size || 0) > 15 * 1024 * 1024) {
    cautions.push('Large file may upload slowly before generation starts.');
  }

  if (aspectRatio > 2.2 || aspectRatio < 0.45) {
    cautions.push('Extreme crop detected; the generator may have to invent missing garment context.');
  } else {
    guidance.push('Crop leaves enough garment context for a believable studio setup.');
  }

  if (orientation === 'Portrait') {
    guidance.push('Portrait references usually pair well with 4:5 or 9:16 outputs.');
  } else if (orientation === 'Landscape') {
    guidance.push('Landscape references preserve more side detail for lookbook-style crops.');
  } else {
    guidance.push('Square references stay flexible for PDP and paid-social crops.');
  }

  studioSuggestedAspectRatio = orientation === 'Square'
    ? '1:1 square'
    : orientation === 'Portrait'
      ? aspectRatio < 0.7 ? '9:16 vertical' : '4:5 portrait'
      : 'original proportion';

  const strongSource = cautions.length === 0;
  const usableSource = cautions.length === 1 && longestEdge >= 1200 && shortestEdge >= 900;
  const readinessLabel = strongSource ? 'Strong Source' : usableSource ? 'Usable Source' : 'Review Source';

  studioSetPill('studioSourceStatus', strongSource ? 'ok' : 'warn', strongSource ? 'Ready' : usableSource ? 'Usable' : 'Review Source');

  badges.innerHTML = [
    readinessLabel,
    `${safeWidth} x ${safeHeight}px`,
    orientation,
    `${megapixels.toFixed(1)} MP`,
    formatFileSize(file?.size || 0),
    file?.type ? file.type.replace('image/', '').toUpperCase() : 'IMAGE',
  ].map(item => `<span class="studio-chip">${escapeHtml(item)}</span>`).join('');

  warnings.innerHTML = [
    ...guidance.map(message => `<div class="studio-source-warning ok">${escapeHtml(message)}</div>`),
    ...cautions.map(message => `<div class="studio-source-warning warn">${escapeHtml(message)}</div>`),
  ].join('');
  studioRefreshSourceSuggestion();
}

function studioCurrentBriefPayload() {
  return {
    bg: studioBg,
    frame: studioDirection.frame,
    energy: studioDirection.energy,
    use_case: studioDirection.use_case,
    aspect_ratio: studioDirection.aspect_ratio,
    notes: document.getElementById('studioStyleNotes')?.value || '',
  };
}

function studioApplyBrief(brief = {}) {
  studioBg = brief.bg && studioLabels[brief.bg] ? brief.bg : studioDefaults.bg;
  studioDirection = {
    frame: brief.frame && studioLabels[brief.frame] ? brief.frame : studioDefaults.frame,
    energy: brief.energy && studioLabels[brief.energy] ? brief.energy : studioDefaults.energy,
    use_case: brief.use_case && studioLabels[brief.use_case] ? brief.use_case : studioDefaults.use_case,
    aspect_ratio: brief.aspect_ratio && studioLabels[brief.aspect_ratio] ? brief.aspect_ratio : studioDefaults.aspect_ratio,
  };
  const notes = document.getElementById('studioStyleNotes');
  if (notes) {
    notes.value = typeof brief.notes === 'string' ? brief.notes : '';
  }
  studioApplyStateToUi();
  studioRefreshBrief();
}

function studioBuildNotes() {
  const customNotes = document.getElementById('studioStyleNotes')?.value.trim();
  const parts = [
    `Framing should be ${studioDirection.frame}.`,
    `Pose and energy should feel ${studioDirection.energy}.`,
    `Compose it like a ${studioDirection.use_case}.`,
    studioDirection.aspect_ratio === 'original proportion'
      ? 'Keep the output in a natural original proportion composition.'
      : `Compose the final shot for a ${studioDirection.aspect_ratio} output.`,
    'Keep the set minimal with no distracting props, extra garments, or text overlays.',
  ];
  if (customNotes) {
    parts.push(customNotes);
  }
  return parts.join(' ');
}

function studioRefreshBrief() {
  const prompt = [
    `Background: ${studioLabel(studioBg)}`,
    `Framing: ${studioLabel(studioDirection.frame)}`,
    `Energy: ${studioLabel(studioDirection.energy)}`,
    `Use Case: ${studioLabel(studioDirection.use_case)}`,
    `Output Ratio: ${studioLabel(studioDirection.aspect_ratio)}`,
    '',
    studioBuildNotes(),
  ].join('\n');

  const promptBox = document.getElementById('studioPromptPreview');
  if (promptBox) {
    promptBox.textContent = prompt;
  }

  const summary = document.getElementById('studioSummaryChips');
  if (summary) {
    summary.innerHTML = [
      `Background: ${studioLabel(studioBg)}`,
      `Framing: ${studioLabel(studioDirection.frame)}`,
      `Energy: ${studioLabel(studioDirection.energy)}`,
      `Use: ${studioLabel(studioDirection.use_case)}`,
      `Ratio: ${studioLabel(studioDirection.aspect_ratio)}`,
    ].map(item => `<span class="studio-chip">${escapeHtml(item)}</span>`).join('');
  }

  const runNote = document.getElementById('studioRunNote');
  if (runNote) {
    const sourceState = studioFile
      ? `Ready to build a ${studioLabel(studioDirection.use_case)} in ${studioLabel(studioBg)}.`
      : 'Best results usually come from a clean product reference, a restrained background, and one clear styling note.';
    runNote.textContent = sourceState;
  }

  studioRefreshSourceSuggestion();
  studioPersistState();
}

function studioRefreshVariantRunSummary() {
  const summary = document.getElementById('studioRunSummary');
  if (summary) {
    summary.textContent = studioVariantCount === 1
      ? 'Generate one refined take from this brief. Use Cmd/Ctrl + Enter for a fast rerun.'
      : `Run ${studioVariantCount} sequential variants from the same brief. The latest run strip will collect them here.`;
  }

  const button = document.getElementById('studioGenBtn');
  if (button && !button.disabled) {
    button.textContent = studioVariantCount === 1
      ? '✦ GENERATE STUDIO SHOT'
      : `✦ GENERATE ${studioVariantCount} VARIANTS`;
  }
}

function studioSetCompareMode(mode, el) {
  studioCompareMode = mode;
  document.querySelectorAll('#studioCompareModes .studio-mini-toggle').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === mode);
  });
  if (el) {
    el.classList.add('active');
  }
  studioPersistUiState();
  studioRenderResultFrame();
}

function studioSetHistoryFilter(filter, el) {
  studioHistoryFilter = filter;
  document.querySelectorAll('#studioHistoryFilters .studio-mini-toggle').forEach(button => {
    button.classList.toggle('active', button.dataset.filter === filter);
  });
  if (el) {
    el.classList.add('active');
  }
  studioPersistUiState();
  studioRenderHistory();
}

function studioToggleRunControls(running) {
  studioIsRunning = running;
  const stopBtn = document.getElementById('studioStopBtn');
  if (stopBtn) {
    stopBtn.style.display = running ? '' : 'none';
    stopBtn.textContent = 'Stop Run';
  }
  studioSyncSourceActions();
}

function studioSyncCurrentResultActions() {
  const favoriteBtn = document.getElementById('studioFavoriteBtn');
  const shortlistBtn = document.getElementById('studioShortlistBtn');
  const approveBtn = document.getElementById('studioApproveBtn');
  const downloadBtn = document.getElementById('studioDownloadBtn');
  if (!favoriteBtn || !shortlistBtn || !approveBtn || !downloadBtn) return;
  if (!studioResultPath) {
    favoriteBtn.style.display = 'none';
    shortlistBtn.style.display = 'none';
    approveBtn.style.display = 'none';
    downloadBtn.style.display = 'none';
    favoriteBtn.textContent = '☆ Favorite';
    shortlistBtn.textContent = '□ Shortlist';
    approveBtn.textContent = '□ Approve';
    return;
  }
  const item = studioSelectedResultItem();
  favoriteBtn.style.display = '';
  shortlistBtn.style.display = '';
  approveBtn.style.display = '';
  downloadBtn.style.display = '';
  favoriteBtn.textContent = item?.favorite ? '★ Favorited' : '☆ Favorite';
  shortlistBtn.textContent = item?.reviewStatus === 'shortlisted'
    ? '✓ Shortlisted'
    : item?.reviewStatus === 'approved'
      ? 'Move To Shortlist'
      : '□ Shortlist';
  approveBtn.textContent = item?.reviewStatus === 'approved' ? '✔ Approved' : '□ Approve';
}

function studioSyncShotNoteActions() {
  const noteField = document.getElementById('studioShotNote');
  const saveBtn = document.getElementById('studioSaveNoteBtn');
  const clearBtn = document.getElementById('studioClearNoteBtn');
  const meta = document.getElementById('studioShotNoteMeta');
  const item = studioSelectedResultItem();
  if (!noteField || !saveBtn || !clearBtn || !meta) return;

  if (!studioResultPath || !item) {
    noteField.disabled = true;
    noteField.value = '';
    saveBtn.disabled = true;
    clearBtn.disabled = true;
    meta.textContent = 'Select or generate a shot to attach notes like "best for PDP", "needs cleaner hem", or "strong ad candidate".';
    return;
  }

  const savedNote = typeof item.shotNote === 'string' ? item.shotNote : '';
  if (noteField.dataset.path !== item.path) {
    noteField.value = savedNote;
    noteField.dataset.path = item.path;
  }
  noteField.disabled = false;
  saveBtn.disabled = noteField.value.trim() === savedNote.trim();
  clearBtn.disabled = !savedNote.trim() && !noteField.value.trim();
  meta.textContent = savedNote.trim()
    ? 'Notes are saved locally with this Studio shot.'
    : 'Save quick internal review notes for this specific Studio output.';
}

function studioSaveShotNoteByPath(path, note) {
  const item = studioHistory.find(entry => entry.path === path);
  if (!item) return;
  item.shotNote = note.trim();
  studioSortHistory();
  studioPersistHistory();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
  analyticsTrack('studio_note_saved', {
    note_length: item.shotNote.length,
    use_case: item.use_case || 'unknown',
    review_status: item.reviewStatus || 'none',
  });
}

function studioSaveCurrentShotNote() {
  if (!studioResultPath) return;
  const noteField = document.getElementById('studioShotNote');
  if (!noteField) return;
  studioSaveShotNoteByPath(studioResultPath, noteField.value || '');
  studioLog('Saved shot note for the current Studio result.', 'success');
}

function studioClearCurrentShotNote() {
  if (!studioResultPath) return;
  const noteField = document.getElementById('studioShotNote');
  if (noteField) {
    noteField.value = '';
  }
  studioSaveShotNoteByPath(studioResultPath, '');
  studioLog('Cleared shot note for the current Studio result.', 'dim');
}

function studioLog(msg, cls = 'info') {
  const box = document.getElementById('studioLog');
  const line = document.createElement('div');
  line.className = `log-line ${cls}`;
  line.textContent = `[${new Date().toLocaleTimeString('en-US', { hour12: false })}] ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function studioClearLog() {
  const box = document.getElementById('studioLog');
  if (!box) return;
  box.innerHTML = '<div class="log-line dim">// Studio log cleared</div>';
}

function studioSetVariantCount(count, el) {
  studioVariantCount = count;
  document.querySelectorAll('#studioVariantChoices .studio-mini-toggle').forEach(button => {
    button.classList.toggle('active', Number(button.dataset.variants) === count);
  });
  if (el) {
    el.classList.add('active');
  }
  studioPersistUiState();
  studioRefreshVariantRunSummary();
}

function studioStopRun() {
  if (!studioIsRunning) return;
  studioRunAbortRequested = true;
  const stopBtn = document.getElementById('studioStopBtn');
  if (stopBtn) {
    stopBtn.textContent = 'Stopping...';
  }
  studioSetPill('studioResultStatus', 'warn', 'Stopping');
  studioLog('Stop requested. Ending the current Studio run...', 'warn');
  if (studioRunController) {
    studioRunController.abort();
  }
}

function studioSetCompareSplit(value) {
  studioCompareSplit = Math.max(0, Math.min(100, Number(value) || 0));
  const overlay = document.getElementById('studioCompareOverlay');
  const divider = document.getElementById('studioCompareDivider');
  const slider = document.getElementById('studioCompareSlider');
  const valueEl = document.getElementById('studioCompareValue');
  if (overlay) {
    const clip = `inset(0 ${100 - studioCompareSplit}% 0 0)`;
    overlay.style.clipPath = clip;
    overlay.style.webkitClipPath = clip;
  }
  if (divider) divider.style.left = `${studioCompareSplit}%`;
  if (slider) slider.value = String(studioCompareSplit);
  if (valueEl) valueEl.textContent = `${studioCompareSplit}%`;
}

function studioRenderResultFrame() {
  const box = document.getElementById('studioResultBox');
  const slider = document.getElementById('studioCompareSlider');
  if (!box) return;

  if (!studioResultPath) {
    box.innerHTML = '<span class="preview-placeholder">RESULT WILL APPEAR HERE</span>';
    if (slider) slider.disabled = true;
    studioSetCompareSplit(studioCompareSplit);
    return;
  }

  const generatedSrc = `/img_preview?path=${encodeURIComponent(studioResultPath)}`;
  const compareAvailability = studioCompareAvailability();
  if (compareAvailability.enabled && studioCompareMode === 'slider') {
    box.innerHTML = `
      <div class="studio-compare-layer">
        <img src="${generatedSrc}" alt="Generated studio result">
      </div>
      <div class="studio-compare-overlay" id="studioCompareOverlay" style="clip-path:inset(0 ${100 - studioCompareSplit}% 0 0);-webkit-clip-path:inset(0 ${100 - studioCompareSplit}% 0 0);">
        <img src="${studioReferenceSrc}" alt="Reference comparison">
      </div>
      <div class="studio-compare-divider" id="studioCompareDivider" style="left:${studioCompareSplit}%"></div>
      <span class="studio-compare-tag left">Reference</span>
      <span class="studio-compare-tag right">Generated</span>
    `;
    if (slider) slider.disabled = false;
    studioSetCompareSplit(studioCompareSplit);
    return;
  }

  box.innerHTML = `
    <div class="studio-compare-layer">
      <img src="${generatedSrc}" alt="Generated studio result">
    </div>
    ${compareAvailability.message ? `<div class="studio-compare-empty">${escapeHtml(compareAvailability.message)}</div>` : ''}
  `;
  if (slider) slider.disabled = true;
  studioSetCompareSplit(studioCompareSplit);
}

function studioRenderVariantFilmstrip() {
  const container = document.getElementById('studioVariantFilmstrip');
  const summary = document.getElementById('studioVariantSummary');
  if (!container) return;

  if (!studioCurrentRun.length) {
    container.innerHTML = '<div class="empty-state">Run one or more variants and they will appear here for quick compare switching.</div>';
    if (summary) {
      summary.textContent = 'Generate a shot to build the latest run strip.';
    }
    return;
  }

  if (summary) {
    summary.textContent = `${studioCurrentRun.length} variant${studioCurrentRun.length === 1 ? '' : 's'} from the latest run. Click any card to compare it.`;
  }

  container.innerHTML = studioCurrentRun.map((item, index) => `
    <button class="studio-variant-card ${studioResultPath === item.path ? 'active' : ''}" type="button" onclick="studioSelectVariant(${index})">
      <div class="studio-variant-thumb">
        <img src="/img_preview?path=${encodeURIComponent(item.path)}" alt="${escapeHtml(item.name || `Variant ${index + 1}`)}">
      </div>
      <div class="studio-variant-meta">
        <span class="studio-variant-name">Variant ${index + 1}</span>
        <span class="studio-variant-sub">${escapeHtml(studioFormatHistoryTime(item.createdAt))}</span>
      </div>
    </button>
  `).join('');
}

function studioSelectVariant(index) {
  const item = studioCurrentRun[index];
  if (!item) return;
  studioResultPath = item.path;
  studioSelectedHistoryPath = item.path;
  studioSetPill('studioResultStatus', 'ok', 'Result Ready');
  studioRenderResultFrame();
  studioRenderVariantFilmstrip();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
}

function studioConfirmRunReplacement() {
  if (!studioCurrentRun.length && !studioResultPath) return true;
  return window.confirm('Replace the current Studio run and load a new reference photo?');
}

function studioResetDirection() {
  studioApplyBrief(studioDefaults);
  studioLog('Brief reset to defaults.', 'dim');
}

function studioResetResult() {
  studioResultPath = null;
  studioSelectedHistoryPath = null;
  studioCurrentRun = [];
  document.getElementById('studioProgress').style.width = '0%';
  studioSetPill('studioResultStatus', 'warn', studioFile ? 'Ready' : 'Idle');
  studioRenderResultFrame();
  studioSetCompareSplit(studioCompareSplit);
  studioRenderVariantFilmstrip();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
}

function studioFormatHistoryTime(ts) {
  if (!ts) return 'Unknown time';
  return new Date(ts).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function studioPersistHistory() {
  writeLocalJson(STUDIO_HISTORY_STORAGE_KEY, studioHistory);
}

function studioSortHistory() {
  studioHistory.sort((a, b) =>
    studioReviewPriority(b) - studioReviewPriority(a) ||
    Number(Boolean(b.favorite)) - Number(Boolean(a.favorite)) ||
    (b.createdAt || 0) - (a.createdAt || 0)
  );
}

function studioRenderHistory() {
  const list = document.getElementById('studioHistoryList');
  if (!list) return;
  const visibleHistory = studioHistory.filter(item => {
    if (studioHistoryFilter === 'favorites') return item.favorite;
    if (studioHistoryFilter === 'shortlisted') return item.reviewStatus === 'shortlisted';
    if (studioHistoryFilter === 'approved') return item.reviewStatus === 'approved';
    return true;
  });

  if (!visibleHistory.length) {
    list.innerHTML = studioHistoryFilter === 'favorites'
      ? '<div class="empty-state">No favorited Studio shots yet. Mark strong outputs with ☆ Favorite to keep them here.</div>'
      : studioHistoryFilter === 'shortlisted'
        ? '<div class="empty-state">No shortlisted Studio shots yet. Use □ Shortlist on promising outputs to collect them here.</div>'
        : studioHistoryFilter === 'approved'
          ? '<div class="empty-state">No approved Studio shots yet. Use □ Approve on ready-to-use outputs to collect them here.</div>'
          : '<div class="empty-state">Generated studio shots will collect here for quick reopening.</div>';
    return;
  }

  if (!studioHistory.length) {
    list.innerHTML = '<div class="empty-state">Generated studio shots will collect here for quick reopening.</div>';
    return;
  }

  list.innerHTML = visibleHistory.map((item, index) => `
    <div class="studio-history-item ${studioSelectedHistoryPath === item.path ? 'active' : ''}">
      <div class="studio-history-thumb">
        <img src="/img_preview?path=${encodeURIComponent(item.path)}" alt="${escapeHtml(item.name || 'Studio shot')}">
      </div>
      <div class="studio-history-meta">
        <div class="studio-history-name-row">
          <div class="studio-history-name">${escapeHtml(item.name || item.path.split('/').pop())}</div>
          <div class="studio-history-tags">
            ${item.reviewStatus ? `<span class="studio-history-tag ${escapeHtml(item.reviewStatus)}">${escapeHtml(studioReviewStatusLabel(item.reviewStatus))}</span>` : ''}
            ${item.favorite ? '<span class="studio-history-tag favorite">★ Favorite</span>' : ''}
          </div>
        </div>
        <div class="studio-history-sub">${escapeHtml(studioFormatHistoryTime(item.createdAt))} · ${escapeHtml(studioLabel(item.use_case || studioDefaults.use_case))} · ${escapeHtml(studioLabel(item.bg || studioDefaults.bg))}</div>
        <div class="studio-history-sub">${escapeHtml(studioLabel(item.frame || studioDefaults.frame))} · ${escapeHtml(studioLabel(item.energy || studioDefaults.energy))} · ${escapeHtml(studioLabel(item.aspect_ratio || studioDefaults.aspect_ratio))}</div>
        ${studioBuildHistorySourceLabel(item) ? `<div class="studio-history-sub">${escapeHtml(studioBuildHistorySourceLabel(item))}</div>` : ''}
        ${item.shotNote ? `<div class="studio-history-sub">${escapeHtml(item.shotNote.length > 108 ? `${item.shotNote.slice(0, 105)}...` : item.shotNote)}</div>` : ''}
        <div class="studio-history-actions">
          <button class="chip-btn small" type="button" data-studio-action="open" data-studio-path="${escapeHtml(item.path)}">Open</button>
          <button class="chip-btn small" type="button" data-studio-action="favorite" data-studio-path="${escapeHtml(item.path)}">${item.favorite ? '★ Saved' : '☆ Favorite'}</button>
          <button class="chip-btn small" type="button" data-studio-action="shortlist" data-studio-path="${escapeHtml(item.path)}">${item.reviewStatus === 'shortlisted' ? '✓ Shortlisted' : item.reviewStatus === 'approved' ? 'Move To Shortlist' : '□ Shortlist'}</button>
          <button class="chip-btn small" type="button" data-studio-action="approve" data-studio-path="${escapeHtml(item.path)}">${item.reviewStatus === 'approved' ? '✔ Approved' : '□ Approve'}</button>
          <button class="chip-btn small" type="button" data-studio-action="reuse" data-studio-path="${escapeHtml(item.path)}">Reuse Brief</button>
        </div>
      </div>
    </div>
  `).join('');
}

function studioLoadHistory() {
  const stored = readLocalJson(STUDIO_HISTORY_STORAGE_KEY, []);
  studioHistory = Array.isArray(stored)
    ? stored.filter(item => item && typeof item.path === 'string').slice(0, 12)
    : [];
  studioSortHistory();
  studioRenderHistory();
}

function studioPersistPresets() {
  writeLocalJson(STUDIO_PRESET_STORAGE_KEY, studioPresets);
}

function studioRenderPresets() {
  const list = document.getElementById('studioPresetList');
  if (!list) return;
  if (!studioPresets.length) {
    list.innerHTML = '<div class="empty-state">Save repeatable brand looks here for one-click reuse.</div>';
    return;
  }

  list.innerHTML = studioPresets.map((preset, index) => `
    <div class="studio-preset-item">
      <div class="studio-preset-head">
        <div class="studio-preset-name">${escapeHtml(preset.name || 'Saved look')}</div>
        <span class="status-pill ok">Saved</span>
      </div>
      <div class="studio-preset-meta">${escapeHtml(studioLabel(preset.use_case || studioDefaults.use_case))} · ${escapeHtml(studioLabel(preset.bg || studioDefaults.bg))} · ${escapeHtml(studioLabel(preset.aspect_ratio || studioDefaults.aspect_ratio))}</div>
      <div class="studio-preset-meta">${escapeHtml(studioLabel(preset.frame || studioDefaults.frame))} · ${escapeHtml(studioLabel(preset.energy || studioDefaults.energy))}</div>
      ${preset.notes ? `<div class="studio-preset-meta">${escapeHtml(preset.notes.length > 88 ? `${preset.notes.slice(0, 85)}...` : preset.notes)}</div>` : ''}
      <div class="studio-preset-actions">
        <button class="chip-btn small" type="button" onclick="studioApplyPreset(${index})">Apply</button>
        <button class="chip-btn small" type="button" onclick="studioRenamePreset(${index})">Rename</button>
        <button class="chip-btn small" type="button" onclick="studioDeletePreset(${index})">Delete</button>
      </div>
    </div>
  `).join('');
}

function studioLoadPresets() {
  const stored = readLocalJson(STUDIO_PRESET_STORAGE_KEY, []);
  studioPresets = Array.isArray(stored)
    ? stored.filter(item => item && typeof item.name === 'string').slice(0, 12)
    : [];
  studioRenderPresets();
}

function studioPushHistory(item) {
  const existing = studioHistory.find(entry => entry.path === item.path) || {};
  studioHistory = [{ ...existing, ...item }, ...studioHistory.filter(entry => entry.path !== item.path)].slice(0, 12);
  studioSortHistory();
  studioPersistHistory();
  studioSelectedHistoryPath = item.path;
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
}

function studioOpenHistory(index) {
  const item = studioHistory[index];
  if (!item) return;
  studioOpenHistoryByPath(item.path);
}

function studioOpenHistoryByPath(path) {
  const item = studioHistory.find(entry => entry.path === path);
  if (!item) return;
  studioResultPath = item.path;
  studioSelectedHistoryPath = item.path;
  studioSetPill('studioResultStatus', 'ok', 'Result Ready');
  studioRenderResultFrame();
  studioRenderVariantFilmstrip();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
  studioLog(`Opened recent shot ${item.name || item.path.split('/').pop()}.`, 'info');
}

function studioReuseHistoryBrief(index) {
  const item = studioHistory[index];
  if (!item) return;
  studioReuseHistoryBriefByPath(item.path);
}

function studioReuseHistoryBriefByPath(path) {
  const item = studioHistory.find(entry => entry.path === path);
  if (!item) return;
  studioApplyBrief(item);
  studioLog(`Reused brief from ${item.name || item.path.split('/').pop()}.`, 'info');
}

function studioClearHistory() {
  studioHistory = [];
  studioSelectedHistoryPath = null;
  studioPersistHistory();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioSyncShotNoteActions();
  studioLog('Studio history cleared.', 'dim');
}

function studioToggleHistoryFavorite(index) {
  const item = studioHistory[index];
  if (!item) return;
  studioToggleHistoryFavoriteByPath(item.path);
}

function studioToggleHistoryFavoriteByPath(path) {
  const item = studioHistory.find(entry => entry.path === path);
  if (!item) return;
  item.favorite = !item.favorite;
  studioSortHistory();
  studioPersistHistory();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  studioLog(item.favorite ? `Favorited ${item.name || item.path.split('/').pop()}.` : `Removed favorite from ${item.name || item.path.split('/').pop()}.`, 'dim');
}

function studioToggleCurrentFavorite() {
  if (!studioResultPath) return;
  studioToggleHistoryFavoriteByPath(studioResultPath);
}

function studioToggleReviewStatusByPath(path, reviewStatus) {
  const item = studioHistory.find(entry => entry.path === path);
  if (!item) return;
  const previousStatus = item.reviewStatus || 'none';
  const nextStatus = item.reviewStatus === reviewStatus ? null : reviewStatus;
  item.reviewStatus = nextStatus;
  studioSortHistory();
  studioPersistHistory();
  studioRenderHistory();
  studioSyncCurrentResultActions();
  analyticsTrack('studio_review_status', {
    next_status: nextStatus || 'cleared',
    previous_status: previousStatus,
    use_case: item.use_case || 'unknown',
    aspect_ratio: item.aspect_ratio || 'unknown',
  });
  if (nextStatus === 'approved') {
    studioLog(`Approved ${item.name || item.path.split('/').pop()}.`, 'success');
  } else if (nextStatus === 'shortlisted') {
    studioLog(`Shortlisted ${item.name || item.path.split('/').pop()}.`, 'info');
  } else {
    studioLog(`Cleared review status for ${item.name || item.path.split('/').pop()}.`, 'dim');
  }
}

function studioToggleCurrentReviewStatus(reviewStatus) {
  if (!studioResultPath) return;
  studioToggleReviewStatusByPath(studioResultPath, reviewStatus);
}

function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      if (document.execCommand('copy')) {
        resolve();
      } else {
        reject(new Error('Copy failed'));
      }
    } catch (error) {
      reject(error);
    } finally {
      textarea.remove();
    }
  });
}

async function studioCopyBrief() {
  const text = document.getElementById('studioPromptPreview')?.textContent?.trim() || '';
  if (!text) return;
  try {
    await copyTextToClipboard(text);
    studioLog('Brief copied to clipboard.', 'success');
  } catch (error) {
    studioLog(`Copy failed: ${error.message}`, 'warn');
  }
}

function studioSavePreset() {
  const suggestedName = `${studioLabel(studioDirection.use_case)} / ${studioLabel(studioBg)}`;
  const name = window.prompt('Name this saved look', suggestedName)?.trim();
  if (!name) return;
  const preset = {
    id: Date.now(),
    name,
    ...studioCurrentBriefPayload(),
  };
  studioPresets = [preset, ...studioPresets.filter(item => item.name.toLowerCase() !== name.toLowerCase())].slice(0, 12);
  studioPersistPresets();
  studioRenderPresets();
  studioLog(`Saved preset "${name}".`, 'success');
}

function studioApplyPreset(index) {
  const preset = studioPresets[index];
  if (!preset) return;
  studioApplyBrief(preset);
  studioLog(`Applied preset "${preset.name}".`, 'info');
}

function studioRenamePreset(index) {
  const preset = studioPresets[index];
  if (!preset) return;
  const name = window.prompt('Rename this saved look', preset.name)?.trim();
  if (!name || name === preset.name) return;
  preset.name = name;
  studioPersistPresets();
  studioRenderPresets();
  studioLog(`Renamed preset to "${name}".`, 'success');
}

function studioDeletePreset(index) {
  const preset = studioPresets[index];
  if (!preset) return;
  studioPresets.splice(index, 1);
  studioPersistPresets();
  studioRenderPresets();
  studioLog(`Deleted preset "${preset.name}".`, 'dim');
}

function studioInitialize() {
  studioRestoreUiState();
  studioSetPill('studioSourceStatus', 'warn', 'Awaiting File');
  studioSetPill('studioResultStatus', 'warn', 'Idle');
  studioSetBoxPlaceholder('studioReferenceBox', 'REFERENCE APPEARS HERE');
  studioSyncSourceActions();
  studioResetSourceDiagnostics();
  studioToggleRunControls(false);
  studioRestoreState();
  studioResetResult();
  studioLoadHistory();
  studioLoadPresets();
  studioSetCompareMode(studioCompareMode);
  studioSetHistoryFilter(studioHistoryFilter);
  studioRefreshVariantRunSummary();
  const historyList = document.getElementById('studioHistoryList');
  historyList?.addEventListener('click', studioHandleHistoryClick);
}

function studioHandleKeydown(event) {
  if (!(event.metaKey || event.ctrlKey) || event.key !== 'Enter') return;
  const studioTab = document.getElementById('tab-studio');
  const generateBtn = document.getElementById('studioGenBtn');
  if (!studioTab?.classList.contains('active') || !studioFile || generateBtn?.disabled) return;
  event.preventDefault();
  studioLog('Keyboard shortcut triggered generation.', 'dim');
  studioGenerate().catch(() => {});
}

function studioHandleHistoryClick(event) {
  const button = event.target.closest('[data-studio-action][data-studio-path]');
  if (!button) return;
  const path = button.dataset.studioPath;
  const action = button.dataset.studioAction;
  if (!path || !action) return;
  if (action === 'open') {
    studioOpenHistoryByPath(path);
  } else if (action === 'favorite') {
    studioToggleHistoryFavoriteByPath(path);
  } else if (action === 'shortlist') {
    studioToggleReviewStatusByPath(path, 'shortlisted');
  } else if (action === 'approve') {
    studioToggleReviewStatusByPath(path, 'approved');
  } else if (action === 'reuse') {
    studioReuseHistoryBriefByPath(path);
  }
}

function studioClearSource() {
  if (studioIsRunning) {
    studioLog('Stop the current Studio run before removing the source photo.', 'warn');
    return;
  }
  const hasActiveState = Boolean(studioFile || studioReferenceSrc || studioCurrentRun.length || studioResultPath);
  if (hasActiveState && !window.confirm('Remove the current source photo and clear the active Studio run? Recent Studio history will stay saved.')) {
    return;
  }

  studioFile = null;
  studioReferenceSrc = null;
  studioSourceOriginalFile = null;
  studioSourceOriginalReferenceSrc = null;
  studioSourceRotation = 0;
  studioSourceCropAspect = null;
  studioSetDropActive(false);
  studioSyncSourceActions();
  studioSetPill('studioSourceStatus', 'warn', 'Awaiting File');
  document.getElementById('studioDropPrimary').textContent = 'DROP PHOTO HERE';
  document.getElementById('studioDropSecondary').textContent = 'Snap a product photo on your phone, then drop it here. A simple hanger or mannequin shot is enough.';
  studioSetSourceMeta(null);
  document.getElementById('studioSourcePreview').style.display = 'none';
  document.getElementById('studioFileInput').value = '';
  const visibleInput = document.getElementById('studioFileInputVisible');
  if (visibleInput) visibleInput.value = '';
  const img = document.getElementById('studioSourceImg');
  img.onload = null;
  img.onerror = null;
  img.removeAttribute('src');
  studioSetBoxPlaceholder('studioReferenceBox', 'REFERENCE APPEARS HERE');
  studioResetSourceDiagnostics();
  studioResetResult();
  const button = document.getElementById('studioGenBtn');
  if (button) {
    button.disabled = true;
    button.textContent = studioVariantCount === 1
      ? '✦ GENERATE STUDIO SHOT'
      : `✦ GENERATE ${studioVariantCount} VARIANTS`;
  }
  studioRefreshVariantRunSummary();
  studioRefreshBrief();
  studioLog('Cleared the current Studio source photo.', 'dim');
}

function studioApplySuggestedRatio() {
  if (!studioSuggestedAspectRatio) return;
  const target = document.querySelector(`.studio-choice[data-group="aspect_ratio"][data-value="${studioSuggestedAspectRatio}"]`);
  if (!target) return;
  studioSelectOption('aspect_ratio', studioSuggestedAspectRatio, target);
  studioLog(`Applied suggested ratio: ${studioLabel(studioSuggestedAspectRatio)}.`, 'info');
}

function studioHandleFileInputChange(input) {
  const file = input?.files?.[0];
  const hiddenInput = document.getElementById('studioFileInput');
  const visibleInput = document.getElementById('studioFileInputVisible');
  if (hiddenInput && input !== hiddenInput) hiddenInput.value = '';
  if (visibleInput && input !== visibleInput) visibleInput.value = '';
  if (!file) return;
  studioFileSelected(file);
}

function studioIsLikelyImageFile(file) {
  if (!file) return false;
  if ((file.type || '').startsWith('image/')) return true;
  return /\.(png|jpe?g|webp|gif|bmp|tiff?|avif|heic|heif)$/i.test(file.name || '');
}

function studioHandleUnsupportedSource(file) {
  studioSetPill('studioSourceStatus', 'warn', 'Unsupported');
  const name = file?.name || 'Selected file';
  document.getElementById('studioSourceMeta').textContent = `${name} could not be recognized as a supported Studio image. Try JPG, PNG, WebP, AVIF, or HEIC.`;
  studioLog(`Unsupported Studio source: ${name}.`, 'warn');
}

function studioOpenFilePicker(event) {
  if (event?.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
  if (event?.target?.closest('label[for="studioFileInput"],label[for="studioFileInputVisible"],input[type="file"]')) return;
  event?.preventDefault();
  const input = document.getElementById('studioFileInput');
  if (!input) return;
  input.value = '';
  if (typeof input.showPicker === 'function') {
    input.showPicker();
  } else {
    input.click();
  }
}

function studioFileSelected(file) {
  if (!file) return;
  if (!studioIsLikelyImageFile(file)) {
    studioHandleUnsupportedSource(file);
    return;
  }
  if (!studioConfirmRunReplacement()) return;
  studioSetDropActive(true);
  studioSetPill('studioSourceStatus', 'warn', 'Loading');
  document.getElementById('studioDropPrimary').textContent = file.name;
  document.getElementById('studioDropSecondary').textContent = 'Reading source photo...';
  studioSetSourceMeta(file);
  studioResetSourceDiagnostics('Reading the selected source photo...');
  studioLog(`Loading source photo ${file.name}...`, 'dim');
  const reader = new FileReader();
  reader.onerror = () => {
    studioSetPill('studioSourceStatus', 'warn', 'Read Failed');
    document.getElementById('studioSourceMeta').textContent = `${file.name} could not be read in the browser. Try exporting it as JPG or PNG first.`;
    studioLog(`Could not read source file ${file.name}.`, 'error');
  };
  reader.onload = e => {
    studioSourceOriginalFile = file;
    studioSourceOriginalReferenceSrc = e.target.result;
    studioSourceRotation = 0;
    studioApplySourceState(file, studioSourceOriginalReferenceSrc, { resetRotation: true });
  };
  reader.readAsDataURL(file);
}

function studioDragOver(e) { e.preventDefault(); studioSetDropActive(true); }
function studioDragLeave(e) {
  const zone = document.getElementById('studioDropZone');
  if (e?.relatedTarget && zone?.contains(e.relatedTarget)) return;
  studioSetDropActive(Boolean(studioFile));
}
function studioDrop(e) {
  e.preventDefault();
  studioDragLeave();
  const file = e.dataTransfer.files[0];
  if (file) studioFileSelected(file);
}

function studioSelectBg(btn) {
  document.querySelectorAll('.studio-swatch').forEach(s => s.classList.remove('active'));
  btn.classList.add('active');
  studioBg = btn.dataset.bg;
  studioRefreshBrief();
}

function studioSelectOption(group, value, el) {
  studioDirection[group] = value;
  document.querySelectorAll(`.studio-choice[data-group="${group}"]`).forEach(choice => choice.classList.remove('active'));
  el.classList.add('active');
  studioRefreshBrief();
}

// ── Studio Models ─────────────────────────────────────────────────────────────

async function studioLoadModels() {
  try {
    const res = await fetch('/studio_models');
    const data = await res.json();
    if (data.ok) {
      studioModels = data.models || [];
      studioRenderModelGrid();
    }
  } catch (e) { /* silent */ }
}

function studioRenderModelGrid() {
  const grid = document.getElementById('studioModelGrid');
  if (!grid) return;
  if (!studioModels.length) {
    grid.innerHTML = '<div class="empty-state">No models saved yet. Add a reference photo or build an AI preset.</div>';
    return;
  }
  grid.innerHTML = studioModels.map(m => {
    const isSelected = m.id === studioSelectedModelId;
    const thumb = m.type === 'reference'
      ? `<img src="/studio_model_photo/${m.id}" class="studio-model-thumb" alt="${m.name}">`
      : `<div class="studio-model-thumb studio-model-thumb-preset">${m.style === 'boho' ? '🌿' : m.style === 'editorial' ? '✦' : '☀'}</div>`;
    return `
      <div class="studio-model-tile ${isSelected ? 'selected' : ''}" onclick="studioSelectModel('${m.id}')">
        ${thumb}
        <div class="studio-model-tile-name">${m.name}</div>
        <div class="studio-model-tile-type">${m.type === 'reference' ? 'Reference' : m.style || 'Preset'}</div>
        <button class="studio-model-delete" type="button" onclick="event.stopPropagation(); studioDeleteModel('${m.id}')">✕</button>
      </div>`;
  }).join('');
}

function studioSelectModel(id) {
  studioSelectedModelId = studioSelectedModelId === id ? null : id;
  studioRenderModelGrid();
  const m = studioModels.find(x => x.id === id);
  if (m && studioSelectedModelId) {
    studioLog(`Model selected: ${m.name} (${m.type === 'reference' ? 'reference photo' : m.style + ' preset'})`, 'info');
  } else {
    studioLog('Model deselected — using default generation.', 'dim');
  }
}

async function studioDeleteModel(id) {
  await fetch(`/studio_delete_model/${id}`, { method: 'DELETE' });
  if (studioSelectedModelId === id) studioSelectedModelId = null;
  await studioLoadModels();
}

function studioOpenAddModel(type) {
  document.getElementById('studioAddReferenceForm').style.display = type === 'reference' ? 'block' : 'none';
  document.getElementById('studioAddPresetForm').style.display = type === 'preset' ? 'block' : 'none';
  document.getElementById('studioModelGrid').style.display = 'none';
}

function studioCloseAddModel() {
  document.getElementById('studioAddReferenceForm').style.display = 'none';
  document.getElementById('studioAddPresetForm').style.display = 'none';
  document.getElementById('studioModelGrid').style.display = 'grid';
  studioRefFileData = null;
  const thumb = document.getElementById('studioRefThumb');
  if (thumb) { thumb.style.display = 'none'; thumb.src = ''; }
}

function studioRefPhotoSelected(input) {
  const file = input.files[0];
  if (!file) return;
  studioRefFileData = file;
  const reader = new FileReader();
  reader.onload = e => {
    const thumb = document.getElementById('studioRefThumb');
    thumb.src = e.target.result;
    thumb.style.display = 'block';
  };
  reader.readAsDataURL(file);
}

async function studioSaveReferenceModel() {
  const name = document.getElementById('studioRefName').value.trim();
  if (!name) { alert('Please enter a name.'); return; }
  if (!studioRefFileData) { alert('Please select a photo.'); return; }
  const form = new FormData();
  form.append('type', 'reference');
  form.append('name', name);
  form.append('photo', studioRefFileData);
  const res = await fetch('/studio_save_model', { method: 'POST', body: form });
  const data = await res.json();
  if (data.ok) {
    studioCloseAddModel();
    await studioLoadModels();
    document.getElementById('studioRefName').value = '';
  } else {
    alert(data.error);
  }
}

function studioPresetPickStyle(value, el) {
  studioPresetStyleChoice = value;
  document.querySelectorAll('#studioPresetStyleChoices .studio-choice').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

async function studioSavePresetModel() {
  const name = document.getElementById('studioPresetName').value.trim();
  if (!name) { alert('Please enter a name.'); return; }
  const form = new FormData();
  form.append('type', 'preset');
  form.append('name', name);
  form.append('style', studioPresetStyleChoice);
  form.append('skin_tone', document.getElementById('studioPresetSkinTone').value);
  form.append('body_type', document.getElementById('studioPresetBodyType').value);
  form.append('hair', document.getElementById('studioPresetHair').value);
  form.append('age_range', document.getElementById('studioPresetAge').value);
  const res = await fetch('/studio_save_model', { method: 'POST', body: form });
  const data = await res.json();
  if (data.ok) {
    studioCloseAddModel();
    await studioLoadModels();
    document.getElementById('studioPresetName').value = '';
  } else {
    alert(data.error);
  }
}

// ─────────────────────────────────────────────────────────────────────────────

async function studioGenerate() {
  if (!studioFile) return;

  const btn = document.getElementById('studioGenBtn');
  const briefSnapshot = { ...studioCurrentBriefPayload() };
  const compiledNotes = studioBuildNotes();
  const totalVariants = studioVariantCount;
  studioRunAbortRequested = false;
  studioToggleRunControls(true);
  btn.disabled = true;
  btn.textContent = totalVariants === 1 ? '✦ GENERATING...' : `✦ GENERATING 1/${totalVariants}...`;
  studioSetPill('studioResultStatus', 'warn', totalVariants === 1 ? 'Generating' : `Generating 1/${totalVariants}`);
  document.getElementById('studioProgress').style.width = '0%';
  document.getElementById('studioLog').innerHTML = '';
  studioCurrentRun = [];
  studioResultPath = null;
  studioSelectedHistoryPath = null;
  document.getElementById('studioDownloadBtn').style.display = 'none';
  studioRenderVariantFilmstrip();
  studioRenderResultFrame();
  studioLog(`Brief locked: ${studioLabel(briefSnapshot.frame)} · ${studioLabel(briefSnapshot.energy)} · ${studioLabel(briefSnapshot.use_case)} · ${studioLabel(briefSnapshot.aspect_ratio)}`, 'info');
  studioLog(`Background set to ${studioLabel(briefSnapshot.bg)}.`, 'dim');
  studioLog(`Source locked: ${(studioSourceOriginalFile?.name || studioFile.name)} · ${studioFormatSourceTransform(studioSourceRotation, studioSourceCropAspect) || 'Original orientation'}`, 'dim');
  studioLog(totalVariants === 1 ? 'Uploading reference photo to Gemini...' : `Launching ${totalVariants} sequential variants from this same brief...`, 'info');
  analyticsTrack('studio_generate_start', {
    variant_count: totalVariants,
    use_case: briefSnapshot.use_case,
    aspect_ratio: briefSnapshot.aspect_ratio,
    background: briefSnapshot.bg,
    source_rotation: studioSourceRotation,
    source_crop: studioSourceCropAspect || 'original',
  });

  let successes = 0;

  for (let index = 0; index < totalVariants; index += 1) {
    if (studioRunAbortRequested) break;

    const variantNumber = index + 1;
    studioSetPill('studioResultStatus', 'warn', totalVariants === 1 ? 'Generating' : `Generating ${variantNumber}/${totalVariants}`);
    btn.textContent = totalVariants === 1 ? '✦ GENERATING...' : `✦ GENERATING ${variantNumber}/${totalVariants}...`;
    studioLog(totalVariants === 1 ? 'Sending brief to Gemini...' : `Variant ${variantNumber}/${totalVariants} — sending brief to Gemini...`, 'info');

    let prog = 0;
    const progInterval = setInterval(() => {
      prog = Math.min(prog + 3, 92);
      const overall = ((variantNumber - 1) + (prog / 100)) / totalVariants * 100;
      document.getElementById('studioProgress').style.width = `${overall}%`;
    }, 650);

    const form = new FormData();
    form.append('image', studioFile);
    form.append('bg_color', briefSnapshot.bg);
    form.append('style_notes', compiledNotes);
    if (studioSelectedModelId) form.append('model_id', studioSelectedModelId);
    studioRunController = new AbortController();

    try {
      const res = await fetch('/studio_generate', { method: 'POST', body: form, signal: studioRunController.signal });
      const data = await readJson(res);
      clearInterval(progInterval);
      document.getElementById('studioProgress').style.width = `${variantNumber / totalVariants * 100}%`;

      if (!res.ok || !data.ok) {
        studioLog(`✕ Variant ${variantNumber}/${totalVariants} failed: ${data.error || `Request failed (${res.status})`}`, 'error');
        continue;
      }

      successes += 1;
      const item = {
        path: data.path,
        name: data.path.split('/').pop(),
        createdAt: Date.now(),
        sourceName: studioSourceOriginalFile?.name || studioFile.name,
        sourceRotation: studioSourceRotation,
        sourceCropAspect: studioSourceCropAspect,
        ...briefSnapshot,
      };

      studioCurrentRun.push(item);
      studioResultPath = data.path;
      studioSelectedHistoryPath = data.path;
      studioRenderResultFrame();
      studioRenderVariantFilmstrip();
      document.getElementById('studioDownloadBtn').style.display = '';

      studioPushHistory(item);
      studioLog(`✓ Variant ${variantNumber}/${totalVariants} → ${item.name}`, 'success');
      studioLog(`Saved in ${prettyPath(data.path)}`, 'dim');
    } catch (err) {
      clearInterval(progInterval);
      document.getElementById('studioProgress').style.width = `${variantNumber / totalVariants * 100}%`;
      if (err.name === 'AbortError') {
        studioRunAbortRequested = true;
        studioLog(`Run stopped during variant ${variantNumber}/${totalVariants}.`, 'warn');
        break;
      }
      studioLog(`✕ Variant ${variantNumber}/${totalVariants} failed: ${err.message}`, 'error');
    } finally {
      studioRunController = null;
    }
  }

  if (studioRunAbortRequested) {
    if (successes) {
      studioSetPill('studioResultStatus', 'warn', `${successes} Ready`);
      studioLog(`Studio run stopped. ${successes} variant${successes === 1 ? '' : 's'} finished before cancel.`, 'warn');
    } else {
      studioSetPill('studioResultStatus', 'warn', 'Stopped');
      studioSetBoxPlaceholder('studioResultBox', 'Studio run stopped before a result was completed.');
      studioRenderVariantFilmstrip();
    }
    analyticsTrack('studio_generate_stopped', {
      variants_requested: totalVariants,
      variants_ready: successes,
      use_case: briefSnapshot.use_case,
      aspect_ratio: briefSnapshot.aspect_ratio,
    });
  } else if (!successes) {
    studioSetPill('studioResultStatus', 'danger', 'Failed');
    studioSetBoxPlaceholder('studioResultBox', 'Generation failed. Adjust the brief and try again.');
    studioRenderVariantFilmstrip();
    analyticsTrack('studio_generate_failure', {
      variants_requested: totalVariants,
      use_case: briefSnapshot.use_case,
      aspect_ratio: briefSnapshot.aspect_ratio,
    });
  } else if (successes < totalVariants) {
    studioSetPill('studioResultStatus', 'warn', `${successes}/${totalVariants} Ready`);
    studioLog(`Finished with partial success: ${successes} of ${totalVariants} variants are ready.`, 'warn');
    analyticsTrack('studio_generate_success', {
      variants_requested: totalVariants,
      variants_ready: successes,
      partial_success: 1,
      use_case: briefSnapshot.use_case,
      aspect_ratio: briefSnapshot.aspect_ratio,
    });
  } else {
    studioSetPill('studioResultStatus', 'ok', totalVariants === 1 ? 'Result Ready' : `${successes} Ready`);
    studioLog(totalVariants === 1 ? 'Studio result ready.' : `All ${successes} variants are ready in the current run strip.`, 'success');
    analyticsTrack('studio_generate_success', {
      variants_requested: totalVariants,
      variants_ready: successes,
      partial_success: 0,
      use_case: briefSnapshot.use_case,
      aspect_ratio: briefSnapshot.aspect_ratio,
    });
  }

  studioToggleRunControls(false);
  btn.disabled = false;
  studioRefreshVariantRunSummary();
}

function studioDownload() {
  if (!studioResultPath) return;
  const historyItem = studioHistory.find(item => item.path === studioResultPath);
  const meta = historyItem || {
    bg: studioBg,
    frame: studioDirection.frame,
    energy: studioDirection.energy,
    use_case: studioDirection.use_case,
    aspect_ratio: studioDirection.aspect_ratio,
  };
  const slug = value => String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 24) || 'studio';
  const ext = studioResultPath.includes('.') ? studioResultPath.slice(studioResultPath.lastIndexOf('.')) : '.jpg';
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '');
  const a = document.createElement('a');
  a.href = `/img_preview?path=${encodeURIComponent(studioResultPath)}`;
  a.download = [
    'studio',
    slug(meta.bg),
    slug(meta.frame),
    slug(meta.energy),
    slug(meta.use_case),
    slug(meta.aspect_ratio),
    stamp,
  ].join('_') + ext;
  analyticsTrack('studio_download', {
    use_case: meta.use_case || 'unknown',
    aspect_ratio: meta.aspect_ratio || 'unknown',
    review_status: historyItem?.reviewStatus || 'none',
  });
  a.click();
}
