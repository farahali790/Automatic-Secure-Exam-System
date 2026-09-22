/* ═══════════════════════════════════════════════════════════
   dashboard.js — Invigilator Dashboard
   static/js/dashboard.js
═══════════════════════════════════════════════════════════ */

const Dashboard = (() => {

  let STUDENTS = [];
  let ALERTS   = [];
  let activeTab         = 'overview';
  let activeFilter      = 'all';
  let activeAlertFilter = 'all';
  let sessionTimerSecs  = 90 * 60;
  let refreshInterval   = null;
  let viewModalStudent  = null;   // student currently open in the view modal

  // ── INIT ──────────────────────────────────────────────
  function init() {
    _fetchAndRender();
    _startSessionTimer();
    _startAutoRefresh();
    _initViewModal();
    const closeBtn = document.getElementById('close-alerts-panel');
    if (closeBtn) closeBtn.addEventListener('click', _closeAlertsPanel);
  }

  async function _fetchAndRender() {
    try {
      const res = await API.invig.getStudents();
      STUDENTS  = res.students || [];
      console.log('[Dashboard] Fetched students:', STUDENTS.length, STUDENTS);
      if (res.error) console.error('[Dashboard] API error:', res.error);

      const ar  = await API.invig.getAlerts();
      ALERTS    = ar.alerts || [];
      console.log('[Dashboard] Fetched alerts:', ALERTS.length);
      if (ar.error) console.error('[Dashboard] API error:', ar.error);
    } catch (e) {
      console.error('[Dashboard] Fetch failed:', e.message, e);
    }
    _renderAll();

    // If the view modal is open, refresh its alert list live
    if (viewModalStudent) {
      const updated = STUDENTS.find(s => s.id === viewModalStudent.id);
      if (updated) _refreshViewModal(updated);
    }
  }

  function _startAutoRefresh() {
    refreshInterval = setInterval(_fetchAndRender, 5000);
  }

  function _renderAll() {
    _renderStudentGrids();
    _renderAlerts();
    _updateStats();
    _updateBadges();
  }

  // ── SESSION COUNTDOWN ─────────────────────────────────
  function _startSessionTimer() {
    const el = document.getElementById('session-timer');
    setInterval(() => {
      if (sessionTimerSecs > 0) sessionTimerSecs--;
      const m = Math.floor(sessionTimerSecs / 60);
      const s = sessionTimerSecs % 60;
      if (el) el.textContent =
        `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')} remaining`;
    }, 1000);
  }

  // ── STATS ─────────────────────────────────────────────
  function _updateStats() {
    const active   = STUDENTS.filter(s => s.status === 'active').length;
    const critical = STUDENTS.filter(s => s.risk >= 60).length;
    const warned   = STUDENTS.filter(s => s.risk >= 25 && s.risk < 60).length;
    const clean    = STUDENTS.filter(s => s.risk < 25).length;

    _set('stat-active',   active);
    _set('stat-critical', critical);
    _set('stat-warnings', warned);
    _set('stat-clean',    clean);
    _set('active-badge',  `${active} active student${active !== 1 ? 's' : ''}`);
  }

  function _updateBadges() {
    const critCount = ALERTS.filter(a => a.level === 'critical').length;
    _set('alerts-count',        critCount);
    _set('sidebar-alert-count', critCount);
    _set('critical-badge',      `● ${critCount} Critical`);

    const summary = document.getElementById('alert-count-summary');
    if (summary) {
      const warnCount = ALERTS.filter(a => a.level === 'warning').length;
      summary.innerHTML =
        `<span class="c">${critCount} critical</span> · ` +
        `<span class="w">${warnCount} warning</span> · ` +
        `<span>${ALERTS.length} total</span>`;
    }
  }

  function _set(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // ── TABS ──────────────────────────────────────────────
  function showTab(tabId) {
    activeTab = tabId;
    ['overview','students','alerts','reports','settings'].forEach(t => {
      const p = document.getElementById('tab-' + t);
      if (p) p.style.display = t === tabId ? 'block' : 'none';
    });
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tabId);
    });
  }

  // ── STUDENT FILTER ────────────────────────────────────
  function setFilter(filter) {
    activeFilter = filter;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    _renderStudentGrids();
  }

  function _applyFilter(students) {
    switch (activeFilter) {
      case 'active':    return students.filter(s => s.status === 'active');
      case 'flagged':   return students.filter(s => s.status === 'flagged' || s.status === 'warned');
      case 'completed': return students.filter(s => s.status === 'completed');
      default:          return students;
    }
  }

  // ── STUDENT TILE ──────────────────────────────────────
  function _buildTile(s) {
    const riskColor = s.risk >= 60 ? 'var(--red)' : s.risk >= 25 ? 'var(--amber)' : 'var(--green)';
    const tileCls   = `student-tile${s.status === 'flagged' ? ' flagged' : s.status === 'warned' ? ' warned' : ''}`;
    const hdCls     = `tile-header${s.status === 'flagged' ? ' flagged' : s.status === 'warned' ? ' warned' : ''}`;
    const tagBadges = s.tags.map(t =>
      `<span class="badge ${s.risk>=60?'badge-red':'badge-amber'}" style="font-size:10px">${t}</span>`
    ).join('');

    return `
      <div class="${tileCls}">
        <div class="${hdCls}">
          <div>
            <div class="tile-name">${s.name}</div>
            <div class="tile-id">${s.id}</div>
          </div>
          <div class="tile-cam-badge"><div class="tile-cam-dot"></div>LIVE</div>
        </div>
        <div class="tile-body">
          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--t3);margin-bottom:8px">
            <span>Progress: <strong style="color:var(--t2)">${s.progress}</strong></span>
            <span>Time: <strong style="color:var(--t2)">${s.time_elapsed}</strong></span>
          </div>
          <div class="risk-row">
            <div class="risk-label">Risk</div>
            <div class="risk-track">
              <div class="risk-fill" style="width:${Math.min(s.risk,100)}%;background:${riskColor}"></div>
            </div>
            <div class="risk-num">${s.risk}</div>
          </div>
          <div class="tile-tags">
            ${tagBadges || '<span style="font-size:10px;color:var(--t3)">No issues detected</span>'}
          </div>
        </div>
        <div class="tile-actions">
          <button class="btn-tile btn-tile-view"  data-id="${s.id}" data-action="view">View</button>
          <button class="btn-tile btn-tile-flag"  data-id="${s.id}" data-action="flag">Flag</button>
          <button class="btn-tile btn-tile-block" data-id="${s.id}" data-action="block">Block</button>
        </div>
      </div>`;
  }

  function _renderStudentGrids() {
    const filtered = _applyFilter(STUDENTS);
    ['ovr-grid','all-grid'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = filtered.length > 0
        ? filtered.map(_buildTile).join('')
        : `<div class="empty-state"><div class="empty-state-icon">👥</div><p>No students found.</p></div>`;
    });
    document.querySelectorAll('.btn-tile').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const {id, action} = btn.dataset;
        if (action === 'view')  openStudent(id);
        if (action === 'flag')  _flagStudent(id);
        if (action === 'block') _blockStudent(id);
      });
    });
  }

  // ── ALERTS ────────────────────────────────────────────
  const ALERT_ICONS = {
    face_mismatch:  '👤',
    phone_detected: '📱',
    extra_person:   '👥',
    book_detected:  '📚',
    gaze_off:       '👁',
    head_turned:    '↔',
    mouth_moving:   '💬',
  };

  function filterAlerts(level) {
    activeAlertFilter = level;
    document.querySelectorAll('.alert-filter-btn').forEach(btn => {
      const isActive = btn.dataset.level === level;
      btn.classList.toggle('active', isActive);
      if (isActive) {
        btn.className = `alert-filter-btn active ${level}`;
      } else {
        btn.className = 'alert-filter-btn';
      }
    });
    _renderAlerts();
  }

  function _buildAlertEntry(a) {
    const levelLabel = a.level === 'critical' ? 'Critical' : a.level === 'warning' ? 'Warning' : 'Info';
    const icon  = a.icon || '⚠';
    const detail = _describeAlert(a);

    return `
      <div class="alert-entry ${a.level}" data-id="${a.id}">
        <div class="alert-icon-wrap">${icon}</div>
        <div class="alert-body">
          <div class="alert-body-top">
            <span class="alert-type-badge">${levelLabel}</span>
            <span class="alert-student-name">${a.student_name || 'Unknown'}</span>
            <span class="alert-student-id">${a.student_id || ''}</span>
          </div>
          <div class="alert-detail">${a.title} — ${detail}</div>
        </div>
        <div class="alert-meta">
          <span class="alert-time">${a.time}</span>
          <span class="alert-score">Score: ${a.score}</span>
          ${!a.reviewed
            ? `<button class="alert-reviewed-btn" onclick="Dashboard.markReviewed(${a.id}, this)">Mark reviewed</button>`
            : '<span style="font-size:10px;color:#334155">✓ Reviewed</span>'}
        </div>
      </div>`;
  }

  function _describeAlert(a) {
    const map = {
      'Face Mismatch':   'Identity could not be verified against enrollment photo',
      'Phone Detected':  'Mobile phone detected in camera frame',
      'Extra Person':    'Additional person detected in camera frame',
      'Book Detected':   'Book or written notes detected in camera frame',
      'Gaze Off-Screen': 'Student gaze deviated beyond allowed threshold',
      'Head Turned':     'Head rotation exceeded 35° yaw or 25° pitch',
      'Mouth Movement':  'Sustained mouth movement detected — possible communication',
    };
    return map[a.title] || 'Suspicious activity detected by AI proctoring module';
  }

  function _renderAlerts() {
    const el = document.getElementById('alert-list');
    if (!el) return;

    const filtered = activeAlertFilter === 'all'
      ? ALERTS
      : ALERTS.filter(a => a.level === activeAlertFilter);

    el.innerHTML = filtered.length > 0
      ? filtered.map(_buildAlertEntry).join('')
      : `<div class="empty-state"><div class="empty-state-icon">✅</div><p>No ${activeAlertFilter === 'all' ? '' : activeAlertFilter + ' '}alerts.</p></div>`;

    // Update side panel
    const panelBody = document.getElementById('alerts-panel-body');
    if (panelBody) {
      const recent = ALERTS.slice(0, 10);
      panelBody.innerHTML = recent.length > 0
        ? recent.map(_buildAlertEntry).join('')
        : `<div class="empty-state"><div class="empty-state-icon">🔔</div><p>No alerts yet.</p></div>`;
    }

    _updateBadges();
  }

  function markReviewed(alertId, btn) {
    fetch(`/api/invig/alerts/${alertId}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + localStorage.getItem('invig_token')
      }
    }).then(() => {
      const a = ALERTS.find(x => x.id === alertId);
      if (a) a.reviewed = true;
      if (btn) {
        btn.outerHTML = '<span style="font-size:10px;color:#334155">✓ Reviewed</span>';
      }
    }).catch(() => {});
  }

  // ── EXPORT CSV ────────────────────────────────────────
  function exportAlerts() {
    if (!ALERTS.length) { Toast.show('info', 'No alerts to export.'); return; }
    const rows = [['ID','Level','Student','Student ID','Type','Score','Time','Date','Reviewed']];
    ALERTS.forEach(a => rows.push([
      a.id, a.level, a.student_name, a.student_id,
      a.title, a.score, a.time, a.date, a.reviewed ? 'Yes' : 'No'
    ]));
    const csv  = rows.map(r => r.map(v => `"${v}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `alerts_${new Date().toISOString().slice(0,10)}.csv`;
    a.click(); URL.revokeObjectURL(url);
  }

  // ── STUDENT ACTIONS ───────────────────────────────────
  async function _flagStudent(id) {
    try {
      await API.invig.flagStudent(id);
      Toast.show('success', `Student ${id} flagged for review.`);
      const s = STUDENTS.find(st => st.id === id);
      if (s) s.status = 'flagged';
      _renderStudentGrids();
    } catch { Toast.show('error', 'Failed to flag student.'); }
  }

  async function _blockStudent(id) {
    const s = STUDENTS.find(st => st.id === id);
    if (!s || !confirm(`Block ${s.name} from the exam?`)) return;
    try {
      await API.invig.blockStudent(id);
      Toast.show('success', `${s.name} has been blocked.`);
      // Close the view modal if this student was open in it
      if (viewModalStudent && viewModalStudent.id === id) _closeViewModal();
      STUDENTS = STUDENTS.filter(st => st.id !== id);
      _renderStudentGrids();
    } catch { Toast.show('error', 'Failed to block student.'); }
  }

  // ── VIEW MODAL ────────────────────────────────────────
  // Injects a modal overlay into the page on first call, then reuses it.
  // The modal shows:
  //   • Student name, ID, status badge, risk bar
  //   • An iframe loading /exam/student/<id>/view — the student's live exam
  //     interface, served read-only by the backend
  //   • All alerts for this student, newest first
  //   • Flag and Block action buttons

  function _initViewModal() {
    if (document.getElementById('student-view-modal')) return;

    const modal = document.createElement('div');
    modal.id = 'student-view-modal';
    modal.innerHTML = `
      <div class="svm-backdrop" id="svm-backdrop"></div>
      <div class="svm-sheet" role="dialog" aria-modal="true" aria-labelledby="svm-title">

        <div class="svm-header">
          <div class="svm-header-left">
            <div id="svm-title" class="svm-name"></div>
            <div class="svm-meta-row">
              <span class="svm-id"></span>
              <span class="svm-status-badge"></span>
            </div>
          </div>
          <div class="svm-header-right">
            <button class="svm-action-btn svm-flag-btn"  id="svm-flag-btn">Flag</button>
            <button class="svm-action-btn svm-block-btn" id="svm-block-btn">Block</button>
            <button class="svm-close-btn" id="svm-close-btn" aria-label="Close">✕</button>
          </div>
        </div>

        <div class="svm-risk-row">
          <span class="svm-risk-label">Risk score</span>
          <div class="svm-risk-track">
            <div class="svm-risk-fill" id="svm-risk-fill"></div>
          </div>
          <span class="svm-risk-num" id="svm-risk-num"></span>
          <span class="svm-risk-state" id="svm-risk-state"></span>
        </div>

        <div class="svm-body">

          <div class="svm-feed-col">
            <div class="svm-section-label">Live exam interface</div>
            <div class="svm-iframe-wrap">
              <iframe id="svm-iframe"
                title="Student exam interface"
                sandbox="allow-scripts allow-same-origin"
                referrerpolicy="no-referrer"
                loading="lazy">
              </iframe>
              <div class="svm-iframe-overlay" id="svm-iframe-overlay">
                <div class="svm-iframe-spinner"></div>
                <span>Loading student view…</span>
              </div>
            </div>
          </div>

          <div class="svm-alerts-col">
            <div class="svm-section-label">
              Alerts for this student
              <span class="svm-alert-count" id="svm-alert-count"></span>
            </div>
            <div class="svm-alert-list" id="svm-alert-list">
              <div class="empty-state"><p>No alerts for this student.</p></div>
            </div>
          </div>

        </div>
      </div>`;

    // Inject modal styles
    const style = document.createElement('style');
    style.textContent = `
      #student-view-modal { position:fixed;inset:0;z-index:9000;display:none;align-items:center;justify-content:center; }
      #student-view-modal.open { display:flex; }
      .svm-backdrop { position:absolute;inset:0;background:rgba(0,0,0,.55);backdrop-filter:blur(2px); }
      .svm-sheet {
        position:relative;z-index:1;background:var(--bg1,#fff);border-radius:14px;
        width:min(1100px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;
        box-shadow:0 24px 64px rgba(0,0,0,.25);
      }
      .svm-header {
        display:flex;align-items:center;justify-content:space-between;
        padding:16px 20px;border-bottom:1px solid var(--border,#e2e8f0);flex-shrink:0;
      }
      .svm-name { font-size:17px;font-weight:600;color:var(--t1,#0f172a); }
      .svm-meta-row { display:flex;align-items:center;gap:8px;margin-top:2px; }
      .svm-id { font-size:12px;color:var(--t3,#94a3b8); }
      .svm-status-badge {
        font-size:11px;font-weight:500;padding:2px 8px;border-radius:20px;
        background:var(--green-bg,#dcfce7);color:var(--green,#16a34a);
      }
      .svm-status-badge.flagged  { background:#fef9c3;color:#854d0e; }
      .svm-status-badge.warned   { background:#fff7ed;color:#c2410c; }
      .svm-status-badge.blocked  { background:#fee2e2;color:#b91c1c; }
      .svm-header-right { display:flex;align-items:center;gap:8px; }
      .svm-action-btn {
        font-size:12px;font-weight:500;padding:5px 14px;border-radius:6px;cursor:pointer;border:none;
      }
      .svm-flag-btn  { background:#fef9c3;color:#854d0e; }
      .svm-block-btn { background:#fee2e2;color:#b91c1c; }
      .svm-close-btn {
        background:none;border:none;cursor:pointer;font-size:18px;
        color:var(--t3,#94a3b8);padding:4px 8px;border-radius:6px;line-height:1;
      }
      .svm-close-btn:hover { background:var(--bg2,#f1f5f9);color:var(--t1,#0f172a); }
      .svm-risk-row {
        display:flex;align-items:center;gap:10px;padding:10px 20px;
        border-bottom:1px solid var(--border,#e2e8f0);flex-shrink:0;
      }
      .svm-risk-label { font-size:12px;color:var(--t3,#94a3b8);min-width:70px; }
      .svm-risk-track { flex:1;height:6px;background:var(--bg3,#e2e8f0);border-radius:3px;overflow:hidden; }
      .svm-risk-fill  { height:100%;border-radius:3px;transition:width .4s; }
      .svm-risk-num   { font-size:13px;font-weight:600;min-width:28px;text-align:right; }
      .svm-risk-state { font-size:11px;font-weight:500;padding:2px 8px;border-radius:20px;min-width:72px;text-align:center; }
      .svm-risk-state.normal     { background:#dcfce7;color:#16a34a; }
      .svm-risk-state.suspicious { background:#fef9c3;color:#854d0e; }
      .svm-risk-state.alert      { background:#fee2e2;color:#b91c1c; }
      .svm-body {
        display:flex;flex:1;overflow:hidden;min-height:0;
      }
      .svm-feed-col {
        flex:1.4;display:flex;flex-direction:column;border-right:1px solid var(--border,#e2e8f0);min-width:0;
      }
      .svm-alerts-col {
        flex:1;display:flex;flex-direction:column;min-width:0;
      }
      .svm-section-label {
        font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;
        color:var(--t3,#94a3b8);padding:12px 16px 8px;flex-shrink:0;
        display:flex;align-items:center;justify-content:space-between;
      }
      .svm-alert-count {
        background:var(--red-bg,#fee2e2);color:var(--red,#b91c1c);
        font-size:10px;font-weight:700;padding:1px 7px;border-radius:20px;
      }
      .svm-iframe-wrap {
        position:relative;flex:1;overflow:hidden;
        background:var(--bg2,#f8fafc);
      }
      #svm-iframe {
        width:100%;height:100%;border:none;display:block;
      }
      .svm-iframe-overlay {
        position:absolute;inset:0;display:flex;flex-direction:column;
        align-items:center;justify-content:center;gap:12px;
        background:var(--bg2,#f8fafc);font-size:13px;color:var(--t3,#94a3b8);
        transition:opacity .3s;pointer-events:none;
      }
      .svm-iframe-overlay.hidden { opacity:0; }
      .svm-iframe-spinner {
        width:28px;height:28px;border:3px solid var(--border,#e2e8f0);
        border-top-color:var(--blue,#3b82f6);border-radius:50%;
        animation:svm-spin .8s linear infinite;
      }
      @keyframes svm-spin { to { transform:rotate(360deg); } }
      .svm-alert-list { flex:1;overflow-y:auto;padding:8px 12px; }
      .svm-alert-item {
        padding:9px 10px;border-radius:7px;margin-bottom:6px;border-left:3px solid transparent;
        background:var(--bg2,#f8fafc);
      }
      .svm-alert-item.critical { border-left-color:var(--red,#ef4444);background:#fff5f5; }
      .svm-alert-item.warning  { border-left-color:var(--amber,#f59e0b);background:#fffbeb; }
      .svm-alert-top  { display:flex;align-items:center;gap:6px;margin-bottom:3px; }
      .svm-alert-icon { font-size:13px; }
      .svm-alert-title { font-size:12px;font-weight:600;color:var(--t1,#0f172a); }
      .svm-alert-time  { font-size:10px;color:var(--t3,#94a3b8);margin-left:auto; }
      .svm-alert-desc  { font-size:11px;color:var(--t2,#475569);line-height:1.4; }
    `;
    document.head.appendChild(style);
    document.body.appendChild(modal);

    document.getElementById('svm-close-btn').addEventListener('click', _closeViewModal);
    document.getElementById('svm-backdrop').addEventListener('click', _closeViewModal);
    document.getElementById('svm-flag-btn').addEventListener('click', () => {
      if (viewModalStudent) _flagStudent(viewModalStudent.id);
    });
    document.getElementById('svm-block-btn').addEventListener('click', () => {
      if (viewModalStudent) _blockStudent(viewModalStudent.id);
    });

    // Hide the loading overlay once the iframe finishes loading
    document.getElementById('svm-iframe').addEventListener('load', () => {
      const overlay = document.getElementById('svm-iframe-overlay');
      if (overlay) overlay.classList.add('hidden');
    });

    // Close on Escape
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') _closeViewModal();
    });
  }

  function openStudent(id) {
    const s = STUDENTS.find(st => st.id === id);
    if (!s) return;
    viewModalStudent = s;
    _populateViewModal(s);
    document.getElementById('student-view-modal').classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function _populateViewModal(s) {
    // Header
    document.querySelector('.svm-name').textContent = s.name;
    document.querySelector('.svm-id').textContent   = s.id;
    const badge = document.querySelector('.svm-status-badge');
    badge.textContent  = s.status.charAt(0).toUpperCase() + s.status.slice(1);
    badge.className    = `svm-status-badge ${s.status}`;

    // Risk bar
    const riskColor = s.risk >= 60 ? 'var(--red,#ef4444)'
                    : s.risk >= 25 ? 'var(--amber,#f59e0b)'
                    : 'var(--green,#22c55e)';
    document.getElementById('svm-risk-fill').style.cssText =
      `width:${Math.min(s.risk,100)}%;background:${riskColor}`;
    document.getElementById('svm-risk-num').textContent = s.risk;
    const stateEl  = document.getElementById('svm-risk-state');
    const stateStr = s.risk >= 100 ? 'alert' : s.risk >= 50 ? 'suspicious' : 'normal';
    stateEl.textContent = stateStr.charAt(0).toUpperCase() + stateStr.slice(1);
    stateEl.className   = `svm-risk-state ${stateStr}`;

    // Iframe — loads the student's exam interface in read-only/view mode
    const iframe  = document.getElementById('svm-iframe');
    const overlay = document.getElementById('svm-iframe-overlay');
    overlay.classList.remove('hidden');
    iframe.src = `/exam/student/${s.id}/view`;

    // Alerts
    _refreshViewModal(s);
  }

  function _refreshViewModal(s) {
    viewModalStudent = s;

    // Re-sync risk bar during live refresh
    const riskColor = s.risk >= 60 ? 'var(--red,#ef4444)'
                    : s.risk >= 25 ? 'var(--amber,#f59e0b)'
                    : 'var(--green,#22c55e)';
    const fillEl = document.getElementById('svm-risk-fill');
    const numEl  = document.getElementById('svm-risk-num');
    if (fillEl) fillEl.style.cssText = `width:${Math.min(s.risk,100)}%;background:${riskColor}`;
    if (numEl)  numEl.textContent = s.risk;

    // Filter and render alerts for this student
    const studentAlerts = ALERTS
      .filter(a => a.student_id === s.id)
      .sort((a, b) => b.id - a.id);   // newest first

    const countEl = document.getElementById('svm-alert-count');
    if (countEl) countEl.textContent = studentAlerts.length || '';

    const listEl = document.getElementById('svm-alert-list');
    if (!listEl) return;

    if (!studentAlerts.length) {
      listEl.innerHTML = `<div class="empty-state"><p>No alerts for this student.</p></div>`;
      return;
    }

    listEl.innerHTML = studentAlerts.map(a => `
      <div class="svm-alert-item ${a.level}">
        <div class="svm-alert-top">
          <span class="svm-alert-icon">${a.icon || ALERT_ICONS[a.type] || '⚠'}</span>
          <span class="svm-alert-title">${a.title}</span>
          <span class="svm-alert-time">${a.time}</span>
        </div>
        <div class="svm-alert-desc">${_describeAlert(a)} · Score: ${a.score}</div>
      </div>`).join('');
  }

  function _closeViewModal() {
    const modal = document.getElementById('student-view-modal');
    if (modal) modal.classList.remove('open');
    document.body.style.overflow = '';
    // Clear the iframe src to stop video/audio from the student's session
    const iframe = document.getElementById('svm-iframe');
    if (iframe) iframe.src = '';
    viewModalStudent = null;
  }

  // ── SEARCH ────────────────────────────────────────────
  function filterStudents(query) {
    const q = query.toLowerCase();
    const filtered = _applyFilter(
      STUDENTS.filter(s =>
        s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
      )
    );
    ['ovr-grid','all-grid'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = filtered.length > 0
        ? filtered.map(_buildTile).join('')
        : `<div class="empty-state"><div class="empty-state-icon">🔍</div><p>No results.</p></div>`;
    });
  }

  // ── ALERTS PANEL ──────────────────────────────────────
  function _closeAlertsPanel() {
    const p = document.getElementById('alerts-panel');
    if (p) p.classList.remove('open');
  }

  function toggleAlertsPanel() {
    const p = document.getElementById('alerts-panel');
    if (p) p.classList.toggle('open');
  }

  return {
    init, showTab, setFilter, filterStudents, openStudent,
    toggleAlertsPanel, filterAlerts, markReviewed, exportAlerts
  };

})();

document.addEventListener('DOMContentLoaded', Dashboard.init);