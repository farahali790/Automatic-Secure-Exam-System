/* ═══════════════════════════════════════════════════════════
   exam.js — Live Exam Engine
   static/js/exam.js
═══════════════════════════════════════════════════════════ */

const Exam = (() => {

  const state = {
    questions:     [],
    currentQ:      0,
    answers:       {},
    flagged:       new Set(),
    timerSecs:     90 * 60,
    timerInterval: null,
    procInterval:  null,
    camStream:     null,
    isSubmitted:   false,
  };

  const FALLBACK_QUESTIONS = [
    { q:'Which design pattern defines a one-to-many dependency so that when one object changes state, all its dependents are notified?', opts:['Singleton','Observer','Factory Method','Decorator'], difficulty:'medium', marks:5 },
    { q:'In Agile development, what is the typical length of a Sprint?', opts:['1 week','2–4 weeks','3 months','6 months'], difficulty:'easy', marks:5 },
    { q:'Which UML diagram best represents the sequence of messages exchanged between objects over time?', opts:['Class Diagram','Use Case Diagram','Sequence Diagram','Component Diagram'], difficulty:'easy', marks:5 },
    { q:'What does the "L" in the SOLID principles stand for?', opts:['Linear Composition','Liskov Substitution','Lazy Loading','Loose Coupling'], difficulty:'medium', marks:5 },
    { q:'Which testing approach tests individual components in isolation?', opts:['Integration Testing','System Testing','Unit Testing','Acceptance Testing'], difficulty:'easy', marks:5 },
    { q:'What is the primary goal of refactoring?', opts:['Add new features','Fix bugs','Improve code structure without changing behaviour','Increase performance'], difficulty:'medium', marks:5 },
    { q:'In version control, what does a "merge conflict" indicate?', opts:['A build error','Two branches modified the same code in incompatible ways','A failed test','Missing dependencies'], difficulty:'medium', marks:5 },
    { q:'Which Agile ceremony is used to reflect on the process and improve team practices?', opts:['Sprint Planning','Daily Standup','Sprint Review','Sprint Retrospective'], difficulty:'easy', marks:5 },
    { q:'What does MVC stand for in software architecture?', opts:['Module View Controller','Model View Controller','Multi-View Component','Managed Visual Code'], difficulty:'easy', marks:5 },
    { q:'Which principle states that a class should have only one reason to change?', opts:['Open-Closed Principle','Single Responsibility Principle','Dependency Inversion','Interface Segregation'], difficulty:'medium', marks:5 },
    { q:'What is a use case diagram primarily used for?', opts:['Database design','System architecture','Capturing system requirements from user perspective','Network topology'], difficulty:'easy', marks:5 },
    { q:'Which model is known as the "waterfall" model?', opts:['Agile','Sequential/Linear SDLC','Spiral','RAD'], difficulty:'easy', marks:5 },
    { q:'What is the purpose of a stub in software testing?', opts:['Replace a real component temporarily','Test UI elements','Generate random data','Monitor network calls'], difficulty:'hard', marks:5 },
    { q:'Which Git command creates a new branch and switches to it?', opts:['git merge','git checkout -b','git pull','git stash'], difficulty:'easy', marks:5 },
    { q:'What does "coupling" mean in software engineering?', opts:['How a module is divided','Degree of interdependence between modules','Number of classes in a module','Code reuse level'], difficulty:'medium', marks:5 },
    { q:'Which diagram shows the static structure of a system through classes and relationships?', opts:['Activity Diagram','Sequence Diagram','Class Diagram','State Diagram'], difficulty:'easy', marks:5 },
    { q:'What does "cohesion" refer to in software design?', opts:['Number of dependencies','How closely related the responsibilities of a module are','Code length','Team organization'], difficulty:'medium', marks:5 },
    { q:'Which testing technique does NOT require knowledge of the internal code structure?', opts:['White-box testing','Unit testing','Black-box testing','Code review'], difficulty:'medium', marks:5 },
    { q:'In software metrics, what does LOC stand for?', opts:['Level of Complexity','Lines of Code','List of Classes','Logic Operation Count'], difficulty:'easy', marks:5 },
    { q:'Which Agile framework uses roles: Scrum Master, Product Owner, and Development Team?', opts:['Kanban','XP (Extreme Programming)','Scrum','SAFe'], difficulty:'easy', marks:5 },
  ];

  // ── INIT ──────────────────────────────────────────────
  async function init() {
    await _loadQuestions();
    await _startCamera();

    // ✅ Create exam session so invigilator can see student
    try {
      await API.exam.start();
      console.log('[Exam] Session started');
    } catch (e) {
      console.warn('[Exam] Could not start session:', e);
    }

    _buildGrid();
    _startTimer();
    _startProctoringLoop();
    _renderQ(0);

    const name    = sessionStorage.getItem('exam_name');
    const titleEl = document.getElementById('exam-bar-title');
    if (name && titleEl) titleEl.textContent = name;
  }

  // ── LOAD QUESTIONS ────────────────────────────────────
  async function _loadQuestions() {
    try {
      const res = await API.exam.getQuestions();
      state.questions = res.questions;
      state.timerSecs = (res.duration || 90) * 60;
    } catch {
      state.questions = FALLBACK_QUESTIONS;
      state.timerSecs = 90 * 60;
    }
  }

  // ── CAMERA ────────────────────────────────────────────
  async function _startCamera() {
    try {
      state.camStream = await navigator.mediaDevices.getUserMedia({ video: true });
      const vid = document.getElementById('exam-video');
      if (vid) vid.srcObject = state.camStream;
    } catch {
      console.warn('[Exam] Camera unavailable.');
    }
  }

  function _stopCamera() {
    if (state.camStream) state.camStream.getTracks().forEach(t => t.stop());
    state.camStream = null;
  }

  // ── TIMER ─────────────────────────────────────────────
  function _startTimer() {
    const display = document.getElementById('exam-timer');
    const pill    = document.getElementById('timer-pill');

    state.timerInterval = setInterval(() => {
      state.timerSecs--;
      const m = Math.floor(state.timerSecs / 60);
      const s = state.timerSecs % 60;
      if (display) display.textContent =
        `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

      if (pill) {
        if      (state.timerSecs <= 60)  pill.className = 'exam-timer danger';
        else if (state.timerSecs <= 300) pill.className = 'exam-timer warn';
      }

      if (state.timerSecs === 300) Toast.show('warning', '⏱ 5 minutes remaining!', 5000);
      if (state.timerSecs === 60)  Toast.show('error',   '⏱ 1 minute remaining!',  5000);
      if (state.timerSecs <= 0)    { clearInterval(state.timerInterval); submitExam(true); }
    }, 1000);
  }

  // ── PROCTORING LOOP ───────────────────────────────────
  function _startProctoringLoop() {
    state.procInterval = setInterval(async () => {
      if (!state.camStream) return;
      try {
        const canvas = document.createElement('canvas');
        const vid    = document.getElementById('exam-video');
        if (!vid) return;
        canvas.width  = vid.videoWidth  || 320;
        canvas.height = vid.videoHeight || 240;
        canvas.getContext('2d').drawImage(vid, 0, 0);
        const frame = canvas.toDataURL('image/jpeg', 0.6).split(',')[1];

        const result = await API.proctor.sendFrame(frame);
        if (result && result.cheat_score >= 60) _showProctoringWarning(result.flags);
      } catch { /* ignore */ }
    }, 4000);
  }

  function _showProctoringWarning(flags) {
    const label = (flags[0] || 'suspicious activity').replace(/_/g, ' ');
    Toast.show('warning', `⚠ Proctoring alert: ${label} detected.`, 5000);
  }

  // ── QUESTION GRID ─────────────────────────────────────
  function _buildGrid() {
    const grid = document.getElementById('q-grid');
    if (!grid) return;
    grid.innerHTML = '';
    state.questions.forEach((_, i) => {
      const btn = document.createElement('div');
      btn.className   = 'q-btn';
      btn.id          = 'qb-' + i;
      btn.textContent = i + 1;
      btn.addEventListener('click', () => _renderQ(i));
      grid.appendChild(btn);
    });
  }

  function _refreshGrid() {
    state.questions.forEach((_, i) => {
      const btn = document.getElementById('qb-' + i);
      if (!btn) return;
      btn.className = 'q-btn';
      if      (i === state.currentQ)           btn.classList.add('current');
      else if (state.flagged.has(i))           btn.classList.add('flagged');
      else if (state.answers[i] !== undefined) btn.classList.add('answered');
    });
  }

  // ── RENDER QUESTION ───────────────────────────────────
  function _renderQ(idx) {
    state.currentQ = idx;
    const q = state.questions[idx];
    if (!q) return;

    const numEl  = document.getElementById('q-num');
    const bodyEl = document.getElementById('q-body');
    const optsEl = document.getElementById('q-opts');
    if (!numEl || !bodyEl || !optsEl) return;

    numEl.textContent  = idx + 1;
    bodyEl.textContent = q.q || q.text || '';

    const metaEl = document.getElementById('q-meta-badges');
    if (metaEl) {
      const diff  = q.difficulty || 'medium';
      const marks = q.marks      || 5;
      metaEl.innerHTML = `
        <span class="diff-badge ${diff}">${diff}</span>
        <span class="text-muted font-mono" style="font-size:11px">${marks} marks</span>`;
    }

    optsEl.innerHTML = '';
    const opts = q.opts || q.options || [];
    opts.forEach((opt, i) => {
      const div = document.createElement('div');
      div.className = 'option' + (state.answers[idx] === i ? ' selected' : '');
      div.innerHTML = `<div class="opt-radio"></div><div class="opt-text">${opt}</div>`;
      div.addEventListener('click', () => _selectAnswer(idx, i));
      optsEl.appendChild(div);
    });

    _refreshGrid();
    _updateNavButtons();
    _updateAnsweredCount();
  }

  // ── ANSWER ────────────────────────────────────────────
  function _selectAnswer(qIdx, optIdx) {
    state.answers[qIdx] = optIdx;
    // Save answer to backend for audit trail
    API.exam.saveAnswer(qIdx, optIdx).catch(() => {});
    _renderQ(qIdx);
  }

  // ── FLAG ──────────────────────────────────────────────
  function flagQuestion() {
    const i = state.currentQ;
    state.flagged.has(i) ? state.flagged.delete(i) : state.flagged.add(i);
    _renderQ(i);
  }

  // ── NAVIGATION ────────────────────────────────────────
  function nextQ() { if (state.currentQ < state.questions.length - 1) _renderQ(state.currentQ + 1); }
  function prevQ() { if (state.currentQ > 0) _renderQ(state.currentQ - 1); }

  function _updateNavButtons() {
    const prev = document.getElementById('prev-btn');
    const next = document.getElementById('next-btn');
    if (!prev || !next) return;
    prev.disabled    = state.currentQ === 0;
    const isLast     = state.currentQ === state.questions.length - 1;
    next.textContent = isLast ? 'Submit ✓' : 'Next →';
    next.onclick     = isLast ? () => submitExam(false) : nextQ;
  }

  function _updateAnsweredCount() {
    const el = document.getElementById('ans-count');
    if (el) el.textContent = Object.keys(state.answers).length;
  }

  // ── SUBMIT ────────────────────────────────────────────
  async function submitExam(forced = false) {
    if (state.isSubmitted) return;

    clearInterval(state.timerInterval);
    clearInterval(state.procInterval);

    const answered   = Object.keys(state.answers).length;
    const total      = state.questions.length;
    const unanswered = total - answered;

    if (!forced && unanswered > 0) {
      const ok = confirm(`You have ${unanswered} unanswered question${unanswered > 1 ? 's' : ''}. Submit anyway?`);
      if (!ok) {
        _startTimer();
        return;
      }
    }

    state.isSubmitted = true;
    _stopCamera();
    Toast.show('info', 'Submitting exam...', 0);

    const timeTaken = 90 * 60 - state.timerSecs;

    try {
      // ✅ Actually submit to backend
      await API.exam.submit(state.answers, state.flagged, timeTaken);
      Toast.show('success', 'Exam submitted successfully!');
      setTimeout(() => {
        window.location.href = `/submitted?answered=${answered}&total=${total}`;
      }, 1200);
    } catch (err) {
      console.error('[Exam] Submit failed:', err);
      Toast.show('error', 'Submission failed. Please try again.');
      state.isSubmitted = false;
      _startTimer();
    }
  }

  return { init, nextQ, prevQ, flagQuestion, submitExam };

})();

document.addEventListener('DOMContentLoaded', Exam.init);