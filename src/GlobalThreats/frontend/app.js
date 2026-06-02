/* Live Threat Radar — app.js */

const GHOST_COLORS = {
  G: '#44AAFF',
  H: '#FF2222',
  O: '#FF9900',
  S: '#CC44FF',
  T: '#00FF88',
};
const SEV_SCALE = { critical: 1.8, high: 1.4, medium: 1.0, low: 0.7 };

let allThreats   = [];
let filtered     = [];
let activeWindow = 'all';
let activeGhost  = 'ALL';
let globe;

// ── Color helpers ─────────────────────────────────────────────────────────────
function ghostColor(ghosts) {
  if (!ghosts || !ghosts.length) return '#888888';
  return GHOST_COLORS[ghosts[0]] || '#888888';
}
function sevClass(sev) { return 'sev-' + (sev || 'low'); }

// ── Init globe ────────────────────────────────────────────────────────────────
function initGlobe() {
  try {
    globe = Globe({ animateIn: true })
      .globeImageUrl('/textures/earth-night.jpg')
      .bumpImageUrl('/textures/earth-topology.png')
      .backgroundImageUrl('/textures/night-sky.png')
      .atmosphereColor('#08F4D6')
      .atmosphereAltitude(0.18)
      .width(window.innerWidth)
      .height(window.innerHeight)
      .pointsData([])
      .pointLat(d => d.geo.lat)
      .pointLng(d => d.geo.lng)
      .pointColor(d => ghostColor(d.threat.ghost))
      .pointAltitude(d => 0.015 + (SEV_SCALE[d.risk.severity] || 1) * 0.015)
      .pointRadius(d => 0.6 + (SEV_SCALE[d.risk.severity] || 1) * 0.22)
      .pointsMerge(false)
      .pointLabel(() => '')
      .onPointHover(onHover)
      .onPointClick(onPointClick)
      .arcsData([])
      .arcStartLat(d => d.startLat)
      .arcStartLng(d => d.startLng)
      .arcEndLat(d => d.endLat)
      .arcEndLng(d => d.endLng)
      .arcColor(d => [d.color, 'rgba(0,0,0,0)'])
      .arcAltitudeAutoScale(0.4)
      .arcStroke(0.4)
      .arcDashLength(0.3)
      .arcDashGap(0.15)
      .arcDashAnimateTime(2500)
      (document.getElementById('globe-container'));

    globe.controls().autoRotate      = true;
    globe.controls().autoRotateSpeed = 0.35;
    globe.controls().enableZoom      = true;

    window.addEventListener('resize', () => {
      globe.width(window.innerWidth).height(window.innerHeight);
    });

    console.log('Globe initialised OK');
  } catch (err) {
    console.error('Globe init error:', err);
    document.getElementById('globe-container').innerHTML =
      '<div style="color:#FF4444;font-family:monospace;padding:2rem;font-size:0.8rem;">' +
      'Globe init error: ' + err.message + '</div>';
  }
}

// ── Arcs between high/critical threat origins ─────────────────────────────────
function buildArcs(threats) {
  const hot = threats.filter(e =>
    e.risk.severity === 'critical' || e.risk.severity === 'high'
  ).slice(0, 24);
  const arcs = [];
  for (let i = 0; i < hot.length - 1; i += 2) {
    arcs.push({
      startLat: hot[i].geo.lat,
      startLng: hot[i].geo.lng,
      endLat:   hot[i + 1].geo.lat,
      endLng:   hot[i + 1].geo.lng,
      color:    ghostColor(hot[i].threat.ghost),
    });
  }
  return arcs;
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadData() {
  setStatus('Fetching threats…');
  try {
    const params = new URLSearchParams();
    if (activeWindow !== 'all') params.set('window', activeWindow);
    if (activeGhost  !== 'ALL') params.set('ghost',  activeGhost);
    const qs = params.toString();
    const r  = await fetch('/api/threats' + (qs ? '?' + qs : ''));
    if (!r.ok) throw new Error('HTTP ' + r.status);
    allThreats = await r.json();
  } catch (e) {
    try {
      allThreats = await (await fetch('/data/threats.json')).json();
    } catch {
      setStatus('Could not load threat data'); return;
    }
  }
  applyTimeline();
  updateHUD();
  setStatus(allThreats.length + ' events · ' + new Date().toLocaleTimeString());
}

function applyTimeline() {
  const pct = parseInt(document.getElementById('timeline-slider').value, 10);
  if (pct >= 100) {
    filtered = allThreats.slice();
    document.getElementById('timeline-val').textContent = 'All time';
  } else {
    const sorted = allThreats.slice().sort((a, b) => a.timestamp > b.timestamp ? 1 : -1);
    filtered = sorted.slice(0, Math.max(1, Math.floor(sorted.length * pct / 100)));
    const last = filtered[filtered.length - 1];
    if (last) document.getElementById('timeline-val').textContent =
      new Date(last.timestamp).toLocaleDateString();
  }
  renderGlobe();
}

// ── Globe render ──────────────────────────────────────────────────────────────
let _renderTimer;
function renderGlobe() {
  clearTimeout(_renderTimer);
  _renderTimer = setTimeout(() => {
    if (!globe) return;
    try {
      globe.pointsData(filtered);
      globe.arcsData(buildArcs(filtered));
    } catch (e) { console.warn('renderGlobe:', e); }
  }, 80);
}

// ── HUD stats ─────────────────────────────────────────────────────────────────
function updateHUD() {
  const now   = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
  const month = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  document.getElementById('stat-today').textContent =
    allThreats.filter(e => e.timestamp >= today).length;
  document.getElementById('stat-month').textContent =
    allThreats.filter(e => e.timestamp >= month).length;
  ['G','H','O','S','T'].forEach(l => {
    document.getElementById('cat-' + l.toLowerCase()).textContent =
      allThreats.filter(e => Array.isArray(e.threat.ghost) && e.threat.ghost.includes(l)).length;
  });
}

function setStatus(msg) {
  document.getElementById('hud-status').textContent = msg;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
const tooltip = document.getElementById('tooltip');

function onHover(point, ev) {
  if (!point) {
    tooltip.classList.add('hidden');
    globe.controls().autoRotate = true;
    return;
  }
  globe.controls().autoRotate = false;
  document.getElementById('tt-title').textContent   = point.threat.title;
  document.getElementById('tt-ghost').textContent   = point.threat.ghost.join(' · ');
  document.getElementById('tt-type').textContent    = point.threat.type;
  document.getElementById('tt-country').textContent = point.source.country_anchor;
  const sevEl = document.getElementById('tt-sev');
  sevEl.textContent = point.risk.severity;
  sevEl.className   = 'tt-sev ' + sevClass(point.risk.severity);
  if (ev) {
    const x = ev.clientX, y = ev.clientY;
    tooltip.style.left = (x + 16 + 230 > window.innerWidth ? x - 236 : x + 16) + 'px';
    tooltip.style.top  = (y + 16 + 120 > window.innerHeight ? y - 120 : y + 16) + 'px';
  }
  tooltip.classList.remove('hidden');
}

// ── Side panel ────────────────────────────────────────────────────────────────
const panel = document.getElementById('side-panel');

function onPointClick(point) {
  if (!point) return;
  tooltip.classList.add('hidden');
  globe.controls().autoRotate = false;

  const gt = document.getElementById('panel-ghost-tag');
  gt.textContent = point.threat.ghost.map(g => '[' + g + ']').join(' ');
  gt.style.color = ghostColor(point.threat.ghost);

  document.getElementById('panel-title').textContent   = point.threat.title;
  document.getElementById('panel-source').textContent  = point.source.name;
  document.getElementById('panel-country').textContent = point.source.country_anchor;
  document.getElementById('panel-desc').textContent    = point.threat.description || 'No description available.';
  document.getElementById('panel-ts').textContent      = new Date(point.timestamp).toLocaleString();

  const sevEl = document.getElementById('panel-sev');
  sevEl.textContent = point.risk.severity;
  sevEl.className   = 'panel-sev ' + sevClass(point.risk.severity);

  const iWrap = document.getElementById('panel-indicators-wrap');
  const iDiv  = document.getElementById('panel-indicators');
  const inds  = point.indicators || {};
  const lines = [
    ...(inds.domains      || []).map(x => '🌐 ' + x),
    ...(inds.ip_addresses || []).map(x => '📡 ' + x),
    ...(inds.urls         || []).map(x => '🔗 ' + x),
    ...(inds.hashes       || []).map(x => '# ' + x),
  ];
  iWrap.style.display = lines.length ? 'block' : 'none';
  iDiv.innerHTML = lines.map(l => '<div>' + l + '</div>').join('');

  const link = document.getElementById('panel-link');
  link.style.display = point.source.url ? 'inline-block' : 'none';
  if (point.source.url) link.href = point.source.url;

  panel.classList.remove('hidden');
  globe.pointOfView({ lat: point.geo.lat, lng: point.geo.lng, altitude: 1.8 }, 1000);
}

document.getElementById('panel-close').addEventListener('click', () => {
  panel.classList.add('hidden');
  globe.controls().autoRotate = true;
});

// ── Filters ───────────────────────────────────────────────────────────────────
document.querySelectorAll('.filter-btn[data-window]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn[data-window]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeWindow = btn.dataset.window;
    loadData();
  });
});

document.querySelectorAll('.cat-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeGhost = btn.dataset.cat;
    loadData();
  });
});


document.getElementById('timeline-slider').addEventListener('input', applyTimeline);

// ── Exports ───────────────────────────────────────────────────────────────────
document.getElementById('btn-json').addEventListener('click', () => {
  dlBlob(new Blob([JSON.stringify(filtered, null, 2)], { type: 'application/json' }), 'ghost_threats.json');
});

document.getElementById('btn-csv').addEventListener('click', () => {
  const cols = ['event_id','timestamp','country','ghost','type','severity'];
  const rows = filtered.map(e => [
    e.event_id, e.timestamp, e.source.country_anchor,
    e.threat.ghost.join('|'), e.threat.type, e.risk.severity,
  ]);
  const csv = [cols, ...rows]
    .map(r => r.map(v => '"' + String(v).replace(/"/g,'""') + '"').join(','))
    .join('\n');
  dlBlob(new Blob([csv], { type: 'text/csv' }), 'ghost_threats.csv');
});

document.getElementById('btn-refresh').addEventListener('click', async () => {
  setStatus('Triggering refresh…');
  try {
    const before = await (await fetch('/api/status')).json();
    await fetch('/api/refresh');
    const deadline = Date.now() + 90_000;
    const poll = setInterval(async () => {
      try {
        const s = await (await fetch('/api/status')).json();
        if (s.last_refresh !== before.last_refresh || Date.now() > deadline) {
          clearInterval(poll);
          loadData();
        } else {
          setStatus('Refreshing… ' + s.total_events + ' events so far');
        }
      } catch (_) { clearInterval(poll); loadData(); }
    }, 2000);
  } catch (_) { setTimeout(loadData, 3000); }
});

function dlBlob(blob, filename) {
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob), download: filename
  });
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
initGlobe();
loadData();
setInterval(loadData, 5 * 60 * 1000);
