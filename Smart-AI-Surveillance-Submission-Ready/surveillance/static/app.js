/* Smart AI Surveillance System - front-end controller.
   Loads all data from the Flask REST API and enforces the UI side of RBAC. */

let ME = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 401) { window.location.href = '/login'; throw new Error('unauth'); }
  return res;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* ---------------- bootstrap ---------------- */
async function boot() {
  lucide.createIcons();
  const res = await api('/api/me');
  const data = await res.json();
  ME = data.user;
  applyRole();
  await Promise.all([loadDashboard(), loadCameras(), loadAlerts(),
                     loadIncidents(), loadReports(), loadWebcamAiStatus()]);
  if (ME.role === 'Admin') loadSettings();
  lucide.createIcons();
  // Refresh the operational panels so new AI events appear without a manual reload.
  window.setInterval(async () => {
    try {
      await Promise.all([loadDashboard(), loadCameras(), loadAlerts(), loadIncidents()]);
    } catch (e) { /* Authentication handler redirects when the session expires. */ }
  }, 5000);
}

function applyRole() {
  document.getElementById('userName').innerText = ME.full_name;
  document.getElementById('userRoleBadge').innerText = ME.title;
  const initials = ME.full_name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  document.getElementById('userAvatar').innerText = initials;
  const showAdmin = ME.role === 'Admin';
  document.querySelectorAll('.admin-only').forEach(el =>
    el.classList.toggle('hidden', !showAdmin));
  // Management is view-only: hide action controls.
  if (ME.role === 'Management') {
    document.querySelectorAll('.action-only').forEach(el => el.classList.add('hidden'));
  }
}

async function logout() {
  await api('/api/logout', { method: 'POST' });
  window.location.href = '/login';
}

/* ---------------- navigation ---------------- */
function switchTab(tabId) {
  if (tabId !== 'cameras') stopLiveCamera();
  document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
  document.getElementById('tab-' + tabId).classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.remove('bg-indigo-600', 'text-white');
    btn.classList.add('text-gray-400');
  });
  const active = document.getElementById('nav-' + tabId);
  if (active) { active.classList.add('bg-indigo-600', 'text-white'); active.classList.remove('text-gray-400'); }
}

/* ---------------- dashboard ---------------- */
async function loadDashboard() {
  const s = await (await api('/api/dashboard/stats')).json();
  document.getElementById('sideCams').innerText = s.online_feeds + '/' + s.connected_feeds;
  const metric = (label, val, sub, cls) => `
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div class="text-gray-400 text-xs font-medium uppercase tracking-wider">${label}</div>
      <div class="text-2xl font-bold ${cls} mt-2 flex items-baseline justify-between">
        <span>${val}</span><span class="text-xs font-normal text-gray-400">${sub}</span></div>
    </div>`;
  document.getElementById('metricsRow').innerHTML =
    metric('Connected Feeds', s.connected_feeds, 'All Operational', 'text-white') +
    metric('Active Anomalies', s.active_anomalies, 'Requires Review', 'text-red-400') +
    metric('Incidents Today', s.incidents_today, s.incidents_resolved + ' Resolved', 'text-white') +
    metric('AI Confidence Avg', s.avg_confidence + '%', 'Optimal', 'text-indigo-400');
}

/* ---------------- cameras ---------------- */
let CAMERAS = [];
async function loadCameras() {
  CAMERAS = (await (await api('/api/cameras')).json()).cameras;
  const cameraSelect = document.getElementById('webcamCameraSelect');
  if (cameraSelect) {
    const previous = cameraSelect.value;
    cameraSelect.innerHTML = CAMERAS.map(c => `<option value="${esc(c.code)}">${esc(c.code)} — ${esc(c.name)}</option>`).join('');
    if (CAMERAS.some(c => c.code === previous)) cameraSelect.value = previous;
  }
  // priority live grid = first 4
  const alerts = (await (await api('/api/alerts')).json()).alerts.filter(a => a.status === 'active');
  const alertByCam = {};
  alerts.forEach(a => { alertByCam[a.cam_code] = a; });
  document.getElementById('liveGrid').innerHTML = CAMERAS.slice(0, 4).map(c => {
    const al = alertByCam[c.code];
    const color = al ? (al.severity === 'critical' ? 'red' : 'yellow') : 'emerald';
    const box = al ? `
      <div class="absolute inset-x-12 inset-y-8 border-2 border-${color}-500 bg-${color}-500/10 rounded p-2">
        <div class="bg-${color}-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded w-max">${esc(al.anomaly_type)} (${al.confidence}%)</div>
      </div>` : '';
    const footer = al ? `
      <div class="p-3 flex justify-between items-center text-xs bg-gray-900">
        <span class="text-${color}-400 font-medium">Alert: ${esc(al.anomaly_type)}</span>
        <button onclick="${al.incident_code ? "switchTab('incidents')" : `openDispatchModal('${esc(c.code)}','${esc(al.anomaly_type)}')`}" class="action-only bg-${color}-600 hover:bg-${color}-700 text-white px-2.5 py-1 rounded font-medium">${al.incident_code ? 'View Incident' : 'Respond'}</button>
      </div>` : `
      <div class="p-3 flex justify-between items-center text-xs text-gray-400 bg-gray-900"><span>Status: Normal Activity</span><span class="font-mono text-[10px]">FPS: 30</span></div>`;
    return `<div class="bg-gray-900 border${al ? '-2 anomaly-alert' : ' border-gray-800'} rounded-xl overflow-hidden relative">
      <div class="relative bg-gray-950 aspect-video">
        <img src="${esc(c.image_url)}" class="object-cover w-full h-full opacity-80">${box}
        <div class="absolute top-3 left-3 bg-gray-950/80 px-2 py-1 rounded text-xs text-white font-mono flex items-center space-x-2"><span class="w-2 h-2 rounded-full bg-${color}-400"></span><span>${esc(c.code)}: ${esc(c.name)}</span></div>
      </div>${footer}</div>`;
  }).join('');

  document.getElementById('cameraGrid').innerHTML = CAMERAS.map(c => `
    <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div class="bg-gray-950 aspect-video relative"><img src="${esc(c.image_url)}" class="w-full h-full object-cover">
        <span class="absolute top-2 left-2 bg-black/70 text-xs font-mono px-2 py-0.5 rounded text-white">${esc(c.code)}</span></div>
      <div class="p-4 space-y-2"><div class="flex justify-between items-center"><h3 class="font-bold text-white text-sm">${esc(c.name)}</h3>
        <span class="bg-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded-full font-semibold">${esc(c.status)}</span></div>
        <p class="text-xs text-gray-400">Zone: ${esc(c.zone)} | Resolution: ${esc(c.resolution)} | AI Module: ${c.ai_module ? 'Active' : 'Off'}</p></div>
    </div>`).join('');
  lucide.createIcons();
}

async function loadWebcamAiStatus() {
  const response = await api('/api/camera/status');
  const status = await response.json();
  const label = document.getElementById('headerAiStatus');
  const dot = document.getElementById('headerAiDot');
  const detail = document.getElementById('webcamModelStatus');
  if (label) label.textContent = status.ready ? 'AI model available' : 'AI model unavailable';
  if (dot) dot.className = 'w-2 h-2 rounded-full ' + (status.ready ? 'bg-emerald-400' : 'bg-amber-400');
  if (detail) {
    detail.textContent = status.ready
      ? 'YOLOv8 ready — detects people and knives; restricted-zone rule enabled.'
      : 'Unavailable: ' + (status.missing_dependencies.length ? 'missing ' + status.missing_dependencies.join(', ') : 'YOLO model file missing') + '.';
  }
}

/* ---------------- browser webcam + live AI analysis ---------------- */
let webcamStream = null;
let webcamTimer = null;
let webcamBusy = false;
let webcamLastAlertRefresh = 0;

async function startLiveCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Camera access requires HTTPS or localhost and a browser that supports getUserMedia.');
    return;
  }
  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    });
    const video = document.getElementById('webcamVideo');
    video.srcObject = webcamStream;
    await video.play();
    document.getElementById('webcamPlaceholder').classList.add('hidden');
    document.getElementById('startWebcamBtn').classList.add('hidden');
    document.getElementById('stopWebcamBtn').classList.remove('hidden');
    document.getElementById('webcamStatus').innerText = 'Camera connected — AI analysis starting';
    await loadWebcamAiStatus();
    webcamTimer = window.setInterval(analyseWebcamFrame, 1200);
    analyseWebcamFrame();
  } catch (err) {
    stopLiveCamera();
    document.getElementById('webcamStatus').innerText = 'Camera unavailable';
    alert('Could not open webcam: ' + (err.message || err.name) + '. Check browser camera permission and close other apps using the camera.');
  }
}

function stopLiveCamera() {
  if (webcamTimer) { clearInterval(webcamTimer); webcamTimer = null; }
  if (webcamStream) { webcamStream.getTracks().forEach(track => track.stop()); webcamStream = null; }
  const video = document.getElementById('webcamVideo');
  if (video) video.srcObject = null;
  const overlay = document.getElementById('webcamOverlay');
  if (overlay) overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  const placeholder = document.getElementById('webcamPlaceholder');
  if (placeholder) placeholder.classList.remove('hidden');
  const start = document.getElementById('startWebcamBtn');
  const stop = document.getElementById('stopWebcamBtn');
  if (start) start.classList.remove('hidden');
  if (stop) stop.classList.add('hidden');
  const status = document.getElementById('webcamStatus');
  if (status) status.innerText = 'Camera stopped';
  webcamBusy = false;
}

async function analyseWebcamFrame() {
  if (webcamBusy || !webcamStream) return;
  const video = document.getElementById('webcamVideo');
  if (!video || video.readyState < 2 || !video.videoWidth) return;
  webcamBusy = true;
  try {
    const capture = document.createElement('canvas');
    capture.width = 640;
    capture.height = 480;
    const ctx = capture.getContext('2d');
    ctx.drawImage(video, 0, 0, capture.width, capture.height);
    const blob = await new Promise(resolve => capture.toBlob(resolve, 'image/jpeg', 0.72));
    if (!blob) throw new Error('Could not capture webcam frame');
    const body = new FormData();
    body.append('frame', blob, 'webcam-frame.jpg');
    body.append('camera_code', document.getElementById('webcamCameraSelect').value || 'CAM-01');
    const response = await fetch('/api/camera/analyze', { method: 'POST', body, credentials: 'same-origin' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'AI analysis failed');
    drawWebcamDetections(data.detections || [], data.restricted_zone, capture.width, capture.height);
    const list = document.getElementById('webcamDetectionList');
    list.innerHTML = data.detections && data.detections.length
      ? data.detections.map(d => `<div class="p-2 rounded border ${d.event ? 'border-red-700 bg-red-950/30 text-red-300' : 'border-gray-800 bg-gray-900 text-gray-300'}"><div class="font-semibold">${esc(d.label)}</div><div class="text-[10px] opacity-75">Confidence: ${d.confidence}%</div></div>`).join('')
      : '<div class="text-emerald-400">No supported threat detected in the latest analysed frame.</div>';
    document.getElementById('webcamStatus').innerText = 'Camera connected — monitoring';
    document.getElementById('webcamLastAnalysis').innerText = 'Last AI analysis: ' + new Date().toLocaleTimeString();
    if (data.alerts_created && data.alerts_created.length) {
      document.getElementById('webcamStatus').innerText = 'Warning: security alert recorded';
      await Promise.all([loadAlerts(), loadIncidents(), loadDashboard()]);
    }
  } catch (err) {
    document.getElementById('webcamStatus').innerText = 'AI analysis error: ' + err.message;
  } finally {
    webcamBusy = false;
  }
}

function drawWebcamDetections(detections, zone, width, height) {
  const canvas = document.getElementById('webcamOverlay');
  if (!canvas) return;
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, width, height);
  if (zone) {
    ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 2; ctx.setLineDash([7, 5]);
    ctx.strokeRect(zone.x1, zone.y1, zone.x2-zone.x1, zone.y2-zone.y1);
    ctx.setLineDash([]);
    ctx.fillStyle = '#f59e0b'; ctx.font = '14px sans-serif'; ctx.fillText('RESTRICTED ZONE', zone.x1 + 4, Math.max(16, zone.y1 - 6));
  }
  (detections || []).forEach(d => {
    ctx.strokeStyle = d.event ? '#ef4444' : '#22c55e'; ctx.lineWidth = 3;
    ctx.strokeRect(d.x1, d.y1, d.x2-d.x1, d.y2-d.y1);
    const label = `${d.label} ${d.confidence}%`;
    ctx.font = 'bold 14px sans-serif';
    const w = ctx.measureText(label).width + 10;
    ctx.fillStyle = d.event ? '#b91c1c' : '#166534';
    ctx.fillRect(d.x1, Math.max(0, d.y1 - 23), w, 22);
    ctx.fillStyle = '#fff'; ctx.fillText(label, d.x1 + 5, Math.max(15, d.y1 - 7));
  });
}

async function openAddCamera() {
  const code = prompt('Camera code (e.g. CAM-05):'); if (!code) return;
  const name = prompt('Camera name:'); if (!name) return;
  const zone = prompt('Zone:'); if (!zone) return;
  const res = await api('/api/cameras', { method: 'POST', body: JSON.stringify({ code, name, zone }) });
  if (res.ok) loadCameras(); else alert((await res.json()).error || 'Failed');
}

/* ---------------- alerts ---------------- */
function sevText(s) { return s === 'critical' ? 'text-red-400' : s === 'warning' ? 'text-yellow-400' : 'text-gray-300'; }

async function loadAlerts() {
  const alerts = (await (await api('/api/alerts')).json()).alerts;
  const active = alerts.filter(a => a.status === 'active');
  document.getElementById('alertCountBadge').innerText = active.length;

  // alerts table
  document.getElementById('alertTableBody').innerHTML = active.map(a => {
    const btnColor = a.severity === 'critical' ? 'red' : 'yellow';
    return `<tr>
      <td class="p-3 font-mono text-indigo-400">${esc(a.alert_code)}</td>
      <td class="p-3">${esc(a.cam_code)} (${esc(a.cam_name)})</td>
      <td class="p-3"><span class="${sevText(a.severity)} font-semibold">${esc(a.anomaly_type)}</span></td>
      <td class="p-3 font-bold">${a.confidence}%</td>
      <td class="p-3 text-gray-400">${esc(a.created_at.slice(11))}</td>
      <td class="p-3"><button onclick="openDispatchModal('${esc(a.cam_code)}','${esc(a.anomaly_type)}')" class="action-only bg-${btnColor}-600 hover:bg-${btnColor}-700 text-white px-2.5 py-1 rounded">Investigate</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="p-4 text-center text-gray-500">No active alerts</td></tr>';

  // dashboard alert feed
  document.getElementById('alertFeed').innerHTML = alerts.map(a => {
    if (a.status === 'active') {
      const c = a.severity === 'critical' ? 'red' : 'yellow';
      const label = a.severity === 'critical' ? 'Critical Security Threat' : 'Behavior Anomaly';
      return `<div class="p-3 bg-${c}-950/30 border border-${c}-900/50 rounded-lg space-y-2">
        <div class="flex items-center justify-between"><span class="text-xs font-bold text-${c}-400 uppercase tracking-wide">${label}</span><span class="text-[10px] text-gray-400">${esc(a.created_at.slice(11, 16))}</span></div>
        <p class="text-sm text-gray-200 font-medium">${esc(a.anomaly_type)}</p>
        <div class="text-xs text-gray-400 flex items-center space-x-4"><span>Cam: <strong>${esc(a.cam_code)}</strong></span><span>Confidence: <strong>${a.confidence}%</strong></span></div>
        ${a.evidence_url ? `<a class="text-xs text-indigo-300 underline" href="${esc(a.evidence_url)}" target="_blank" rel="noopener">View captured evidence</a>` : ''}
        <div class="pt-2 flex space-x-2 action-only">
          <button onclick="${a.incident_code ? "switchTab('incidents')" : `openDispatchModal('${esc(a.cam_code)}','${esc(a.anomaly_type)}')`}" class="flex-1 bg-${c}-600 hover:bg-${c}-700 text-white text-xs py-1.5 rounded font-medium">${a.incident_code ? 'View Incident' : 'Log Incident'}</button>
          <button onclick="dismissAlert(${a.id})" class="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs px-2.5 py-1.5 rounded">False Alarm</button>
        </div></div>`;
    }
    return `<div class="p-3 bg-gray-950/50 border border-gray-800 rounded-lg space-y-1 opacity-60">
      <div class="flex items-center justify-between"><span class="text-xs font-bold text-gray-400 uppercase tracking-wide">${esc(a.anomaly_type)}</span><span class="text-[10px] text-gray-500">${esc(a.created_at.slice(11, 16))}</span></div>
      <div class="text-xs text-emerald-400">Resolved</div></div>`;
  }).join('');
  if (ME && ME.role === 'Management') document.querySelectorAll('.action-only').forEach(el => el.classList.add('hidden'));
  lucide.createIcons();
}

async function dismissAlert(id) {
  await api('/api/alerts/' + id + '/dismiss', { method: 'POST' });
  loadAlerts(); loadDashboard();
}

/* ---------------- incidents ---------------- */
function incStatusBadge(status) {
  const map = { 'Resolved': 'emerald', 'In Progress': 'yellow', 'Dispatched': 'red', 'Open': 'indigo' };
  const c = map[status] || 'gray';
  return `<span class="bg-${c}-500/20 text-${c}-400 px-2 py-0.5 rounded-full text-[10px]">${esc(status)}</span>`;
}

async function loadIncidents() {
  const rows = (await (await api('/api/incidents')).json()).incidents;
  document.getElementById('incidentTableBody').innerHTML = rows.map(i => {
    const action = i.status === 'Resolved'
      ? '<span class="text-gray-500">Archived</span>'
      : `<button onclick="resolveIncident(${i.id})" class="action-only bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded">Mark Resolved</button>`;
    return `<tr>
      <td class="p-3 font-mono text-indigo-400">${esc(i.incident_code)}</td>
      <td class="p-3 font-medium text-white">${esc(i.incident_type)}</td>
      <td class="p-3">${esc(i.assigned_officer || '-')}</td>
      <td class="p-3">${incStatusBadge(i.status)}</td>
      <td class="p-3 text-gray-400">${esc(i.created_at.slice(0, 16))}</td>
      <td class="p-3">${action}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="p-4 text-center text-gray-500">No incidents logged</td></tr>';
  if (ME && ME.role === 'Management') document.querySelectorAll('.action-only').forEach(el => el.classList.add('hidden'));
}

async function resolveIncident(id) {
  await api('/api/incidents/' + id + '/resolve', { method: 'POST' });
  loadIncidents(); loadDashboard();
}

/* ---------------- reports ---------------- */
async function loadReports() {
  const t = (await (await api('/api/reports/anomaly-types')).json()).types;
  const colors = ['indigo', 'yellow', 'emerald', 'red', 'sky'];
  document.getElementById('anomalyBars').innerHTML = t.map((x, i) => `
    <div><div class="flex justify-between text-gray-400 mb-1"><span>${esc(x.type)}</span><span>${x.pct}%</span></div>
      <div class="w-full bg-gray-800 rounded-full h-2"><div class="bg-${colors[i % colors.length]}-500 h-2 rounded-full" style="width:${x.pct}%"></div></div></div>`).join('');
  const a = await (await api('/api/reports/accuracy')).json();
  document.getElementById('accuracyStats').innerHTML = `
    <div class="flex justify-between"><span class="text-gray-400">True Positives:</span><span class="text-emerald-400 font-bold">${a.true_positive}%</span></div>
    <div class="flex justify-between"><span class="text-gray-400">False Positive Rate:</span><span class="text-yellow-400 font-bold">${a.false_positive}%</span></div>
    <div class="flex justify-between"><span class="text-gray-400">Avg Response Delay:</span><span class="text-white font-bold">${a.avg_response_minutes} minutes</span></div>`;
}

/* ---------------- settings (admin) ---------------- */
async function loadSettings() {
  const res = await api('/api/settings');
  if (!res.ok) return;
  const s = (await res.json()).settings;
  document.getElementById('cutoffRange').value = s.confidence_cutoff || 80;
  document.getElementById('cutoffVal').innerText = s.confidence_cutoff || 80;
  document.getElementById('loiterInput').value = s.loitering_seconds || 45;
  document.getElementById('sideModel').innerText = s.ai_model || 'YOLOv8-Anomaly';
}

async function saveSettings() {
  await api('/api/settings', { method: 'PUT', body: JSON.stringify({
    confidence_cutoff: document.getElementById('cutoffRange').value,
    loitering_seconds: document.getElementById('loiterInput').value,
  }) });
  const s = document.getElementById('settingsSaved');
  s.classList.remove('hidden'); setTimeout(() => s.classList.add('hidden'), 1500);
}

/* ---------------- modal / dispatch ---------------- */
function openDispatchModal(cam, type) {
  document.getElementById('modalTitle').innerText = 'Dispatch Security Personnel';
  document.getElementById('modalType').value = type || '';
  document.getElementById('modalCam').value = cam || '';
  document.getElementById('modalNotes').value = '';
  document.getElementById('dispatchModal').classList.remove('hidden');
}

function openNewIncidentModal() {
  document.getElementById('modalTitle').innerText = 'Manual Incident Entry';
  document.getElementById('modalType').value = '';
  document.getElementById('modalCam').value = '';
  document.getElementById('modalNotes').value = '';
  document.getElementById('dispatchModal').classList.remove('hidden');
}

function closeModal() { document.getElementById('dispatchModal').classList.add('hidden'); }

async function submitDispatch() {
  const body = {
    incident_type: document.getElementById('modalType').value.trim(),
    camera_ref: document.getElementById('modalCam').value.trim(),
    assigned_officer: document.getElementById('modalOfficer').value,
    notes: document.getElementById('modalNotes').value.trim(),
    status: 'Dispatched',
  };
  if (!body.incident_type) { alert('Incident type is required'); return; }
  const res = await api('/api/incidents', { method: 'POST', body: JSON.stringify(body) });
  if (res.ok) { closeModal(); await loadIncidents(); await loadDashboard(); switchTab('incidents'); }
  else alert((await res.json()).error || 'Failed to save incident');
}

boot();
