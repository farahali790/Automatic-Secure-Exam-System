# Wire the invigilator dashboard to the real backend.

p = 'static/js/dashboard.js'
s = open(p, encoding='utf-8').read()
orig = s

# ============ PATCH 1: empty the hardcoded STUDENTS array ============
old_students = """  let STUDENTS = [
    { id:'BUE-21-001', name:'Ahmed Hassan',   risk:72, status:'flagged', progress:'65%', time_elapsed:'47m', tags:['Phone detected','Gaze off-screen'] },
    { id:'BUE-21-002', name:'Sara Mostafa',   risk:44, status:'warned',  progress:'40%', time_elapsed:'47m', tags:['Head turned'] },
    { id:'BUE-21-003', name:'Omar Khalil',    risk:6,  status:'active',  progress:'55%', time_elapsed:'47m', tags:[] },
    { id:'BUE-21-004', name:'Nour Abdelaziz', risk:88, status:'flagged', progress:'30%', time_elapsed:'47m', tags:['Extra person','Face mismatch'] },
    { id:'BUE-21-005', name:'Youssef Salem',  risk:38, status:'warned',  progress:'70%', time_elapsed:'47m', tags:['Lip movement'] },
    { id:'BUE-21-006', name:'Farah Ali',      risk:3,  status:'active',  progress:'80%', time_elapsed:'47m', tags:[] },
    { id:'BUE-21-007', name:'Mariam Nabil',   risk:0,  status:'active',  progress:'90%', time_elapsed:'47m', tags:[] },
    { id:'BUE-21-008', name:'Karim Saad',     risk:29, status:'warned',  progress:'50%', time_elapsed:'47m', tags:['Gaze off-screen'] },
    { id:'BUE-21-009', name:'Dina Fouad',     risk:0,  status:'active',  progress:'60%', time_elapsed:'47m', tags:[] },
    { id:'BUE-21-010', name:'Tarek Ibrahim',  risk:15, status:'active',  progress:'45%', time_elapsed:'47m', tags:[] },
  ];"""
new_students = "  let STUDENTS = [];   // populated from /api/invig/students"
if old_students in s:
    s = s.replace(old_students, new_students)
    print('emptied hardcoded STUDENTS')
elif 'let STUDENTS = [];' in s:
    print('STUDENTS already empty')
else:
    print('WARN: STUDENTS array — pattern differs from expected')

# ============ PATCH 2: empty the hardcoded ALERTS array ============
old_alerts = """  let ALERTS = [
    { level:'crit', icon:'📱', title:'Phone detected — Ahmed Hassan',   sub:'YOLOv8n detected a mobile phone in frame for 4 seconds.',        time:'10:43:12' },
    { level:'crit', icon:'👤', title:'Extra person — Nour Abdelaziz',   sub:'A second individual detected in camera frame.',                   time:'10:41:55' },
    { level:'warn', icon:'👁', title:'Gaze off-screen — Ahmed Hassan',  sub:'Student looked off-screen for more than 5 seconds.',              time:'10:40:30' },
    { level:'warn', icon:'↔', title:'Head turned — Sara Mostafa',       sub:'Yaw angle exceeded 30° threshold for 3 seconds.',                 time:'10:38:17' },
    { level:'warn', icon:'👄', title:'Lip movement — Youssef Salem',    sub:'Sustained mouth movement detected for 6 seconds.',                time:'10:36:02' },
    { level:'info', icon:'🔄', title:'Face re-verified — Karim Saad',   sub:'Periodic re-verification passed. Confidence: 94.1%',              time:'10:34:00' },
  ];"""
new_alerts = "  let ALERTS = [];     // populated from /api/invig/alerts"
if old_alerts in s:
    s = s.replace(old_alerts, new_alerts)
    print('emptied hardcoded ALERTS')
elif 'let ALERTS = [];' in s:
    print('ALERTS already empty')
else:
    print('WARN: ALERTS array — pattern differs from expected')

# ============ PATCH 3: fetch on init so dashboard fills immediately ============
old_init = """  function init() {
    _renderAll();
    _startSessionTimer();
    _startAutoRefresh();"""
new_init = """  function init() {
    _fetchAndRender();              // initial pull before first paint
    _startSessionTimer();
    _startAutoRefresh();"""
if old_init in s:
    s = s.replace(old_init, new_init)
    print('init() now does initial fetch')

# Insert the helper function right after init()'s closing brace
helper_anchor = """  // ── AUTO REFRESH (from your system — every 5s) ────────"""
helper = """  // ── INITIAL + REFRESHED FETCH ─────────────────────────
  async function _fetchAndRender() {
    try {
      const res = await API.invig.getStudents();
      STUDENTS  = res.students || [];
      const ar  = await API.invig.getAlerts();
      ALERTS    = ar.alerts || [];
    } catch (e) {
      console.warn('[Dashboard] fetch failed:', e);
    }
    _renderAll();
  }

""" + helper_anchor
if helper_anchor in s and '_fetchAndRender' not in s.split(helper_anchor)[0]:
    s = s.replace(helper_anchor, helper)
    print('added _fetchAndRender helper')

# ============ PATCH 4: wire the auto-refresh to use _fetchAndRender ============
old_refresh = """    refreshInterval = setInterval(async () => {
      try {
        // Uncomment when backend ready:
        // const res = await API.invig.getStudents();
        // STUDENTS = res.students;
        // const alertRes = await API.invig.getAlerts();
        // ALERTS = alertRes.alerts;
        _renderStudentGrids();
        _renderAlerts();
      } catch { /* silently ignore refresh errors */ }
    }, 5000);"""
new_refresh = """    refreshInterval = setInterval(_fetchAndRender, 5000);"""
if old_refresh in s:
    s = s.replace(old_refresh, new_refresh)
    print('wired auto-refresh to backend')

# ============ PATCH 5: uncomment flag/block backend calls ============
s = s.replace('// await API.invig.flagStudent(id);',
              'await API.invig.flagStudent(id);')
s = s.replace('// await API.invig.blockStudent(id);',
              'await API.invig.blockStudent(id);')
print('uncommented flag/block calls')

# ============ Save ============
if s != orig:
    open(p, 'w', encoding='utf-8').write(s)
    print('\nDashboard wired up.')
else:
    print('\nNo changes made.')