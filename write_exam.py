import os

# ---- Patch 1: add API.exam.start() to api.js ----
p = 'static/js/api.js'
s = open(p, encoding='utf-8').read()
old = """    getQuestions() {
      return api.get('/api/exam/questions');
    },"""
new = """    getQuestions() {
      return api.get('/api/exam/questions');
    },

    /**
     * POST /api/exam/start
     * Creates an active ExamSession so proctoring alerts can be persisted.
     */
    start() {
      return api.post('/api/exam/start', {});
    },"""
if old in s:
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('api.js: added API.exam.start()')
elif 'start()' in s:
    print('api.js: already has start() — skipping')
else:
    print('api.js: WARNING — could not locate insertion point')

# ---- Patch 2: exam.js — uncomment sendFrame ----
p = 'static/js/exam.js'
s = open(p, encoding='utf-8').read()
old_send = """        // Uncomment when backend is ready:
        // const result = await API.proctor.sendFrame(frame);
        // if (result.cheat_score > 60) _showProctoringWarning(result.flags);"""
new_send = """        const result = await API.proctor.sendFrame(frame);
        if (result && result.cheat_score >= 60) _showProctoringWarning(result.flags);"""
if old_send in s:
    s = s.replace(old_send, new_send)
    print('exam.js: uncommented sendFrame call')
else:
    print('exam.js: sendFrame already uncommented or pattern not found')

# ---- Patch 3: exam.js — call API.exam.start() during init ----
old_init = """    await _loadQuestions();
    await _startCamera();
    _buildGrid();"""
new_init = """    await _loadQuestions();
    await _startCamera();
    try { await API.exam.start(); } catch (e) { console.warn('[Exam] Could not start session:', e); }
    _buildGrid();"""
if old_init in s:
    s = s.replace(old_init, new_init)
    print('exam.js: added API.exam.start() call in init')
elif 'API.exam.start()' in s:
    print('exam.js: already calls API.exam.start() — skipping')
else:
    print('exam.js: WARNING — could not locate init block')

open(p, 'w', encoding='utf-8').write(s)
print('\nDone.')