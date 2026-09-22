/* ═══════════════════════════════════════════════════════════
   api.js — SecureExam API Client
   static/js/api.js
═══════════════════════════════════════════════════════════ */

class APIClient {
  constructor(baseURL = 'http://localhost:5000') {
    this.baseURL = baseURL;
    this.headers = { 'Content-Type': 'application/json' };
  }

  async request(method, path, body = null, opts = {}) {
    const url = this.baseURL + path;
    const config = {
      method,
      headers: { ...this.headers, ...opts.headers },
      credentials: 'include',
    };
    if (body) config.body = JSON.stringify(body);

    try {
      const res = await fetch(url, config);

      if (res.status === 401) {
        this.clearToken();
        document.dispatchEvent(new Event('unauthorized'));
        throw new Error('Unauthorized');
      }

      const data = await res.json();

      if (!res.ok) {
        const err = new Error(data.message || `API error ${res.status}`);
        err.status = res.status;
        err.data   = data;
        throw err;
      }

      return data;
    } catch (err) {
      console.error(`[API] ${method} ${path}`, err.message);
      throw err;
    }
  }

  get(path, opts)        { return this.request('GET',  path, null, opts); }
  post(path, body, opts) { return this.request('POST', path, body, opts); }
  put(path, body, opts)  { return this.request('PUT',  path, body, opts); }
  delete(path, opts)     { return this.request('DELETE', path, null, opts); }

  setToken(token) {
    this.headers['Authorization'] = `Bearer ${token}`;
    localStorage.setItem('se_token', token);
  }
  clearToken() {
    delete this.headers['Authorization'];
    localStorage.removeItem('se_token');
    localStorage.removeItem('se_student_id');
    localStorage.removeItem('invig_token');
  }
  loadToken() {
    // Load invigilator token if on invigilator page, else student token
    const isInvig = window.location.pathname.includes('invigilator');
    const t = isInvig
      ? localStorage.getItem('invig_token')
      : localStorage.getItem('se_token');
    if (t) this.headers['Authorization'] = `Bearer ${t}`;
  }
}

// ── Singleton ─────────────────────────────────────────────
const api = new APIClient();

api.loadToken();

// 401 handler — redirect to correct login page
document.addEventListener('unauthorized', () => {
  const isInvig = window.location.pathname.includes('invigilator');
  window.location.href = isInvig ? '/invigilator_login' : '/student_login';
});


/* ══════════════════════════════════════════════════════════
   NAMESPACED API CALLS
══════════════════════════════════════════════════════════ */
const API = {

  auth: {
    login(studentId, password) {
      return api.post('/api/auth/login', { student_id: studentId, password })
        .then(res => {
          if (res.token) {
            api.setToken(res.token);
            localStorage.setItem('se_student_id', studentId);
          }
          return res;
        });
    },

    logout() {
      return api.post('/api/auth/logout').finally(() => api.clearToken());
    },

    invigLogin(email, password) {
      return api.post('/api/auth/invig', { email, password })
        .then(res => {
          if (res.token) {
            // Save under both keys so dashboard.js and api.js both find it
            api.headers['Authorization'] = `Bearer ${res.token}`;
            localStorage.setItem('invig_token', res.token);
            localStorage.setItem('se_token', res.token);
          }
          return res;
        });
    },
  },

  enroll: {
    capture(frameBase64, index) {
      return api.post('/api/enroll/capture', { frame: frameBase64, index });
    },
    confirm() {
      return api.post('/api/enroll/confirm');
    },
  },

  verify: {
    check(frameBase64) {
      return api.post('/api/verify', { frame: frameBase64 });
    },
  },

  exam: {
    getQuestions() {
      return api.get('/api/exam/questions');
    },
    start() {
      return api.post('/api/exam/start', {});
    },
    saveAnswer(questionIndex, answerIndex) {
      return api.post('/api/exam/answer', { question: questionIndex, answer: answerIndex });
    },
    submit(answers, flagged, timeTaken) {
      return api.post('/api/exam/submit', {
        answers,
        flagged:    [...flagged],
        time_taken: timeTaken,
      });
    },
  },

  proctor: {
    sendFrame(frameBase64) {
      return api.post('/api/proctor/frame', { frame: frameBase64 });
    },
  },

  invig: {
    getStudents()    { return api.get('/api/invig/students'); },
    getAlerts()      { return api.get('/api/invig/alerts'); },
    getStudent(id)   { return api.get(`/api/invig/student/${id}`); },
    flagStudent(id)  { return api.post(`/api/invig/student/${id}/flag`); },
    blockStudent(id) { return api.post(`/api/invig/student/${id}/block`); },
  },
};


/* ══════════════════════════════════════════════════════════
   TOAST NOTIFICATIONS
══════════════════════════════════════════════════════════ */
const Toast = {
  _el: null,
  _timer: null,

  _ensure() {
    if (!this._el) {
      this._el = document.createElement('div');
      this._el.id = 'se-toast';
      Object.assign(this._el.style, {
        position: 'fixed', top: '20px', right: '20px',
        zIndex: '9999', minWidth: '280px', display: 'none',
        borderRadius: '10px', padding: '12px 16px',
        fontFamily: 'var(--f-body, sans-serif)',
        fontSize: '13px', fontWeight: '500',
        boxShadow: '0 8px 28px rgba(0,0,0,.14)',
        transition: 'opacity .25s ease',
      });
      document.body.appendChild(this._el);
    }
  },

  show(type, message, duration = 3000) {
    this._ensure();
    clearTimeout(this._timer);
    const styles = {
      success: { bg: '#f0fdf4', color: '#15803d', border: '1px solid rgba(22,163,74,.25)' },
      error:   { bg: '#fef2f2', color: '#991b1b', border: '1px solid rgba(220,38,38,.25)' },
      warning: { bg: '#fffbeb', color: '#92400e', border: '1px solid rgba(217,119,6,.25)'  },
      info:    { bg: '#eff3ff', color: '#1e3fad', border: '1px solid rgba(42,82,232,.2)'   },
    };
    const s = styles[type] || styles.info;
    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    Object.assign(this._el.style, {
      background: s.bg, color: s.color, border: s.border,
      display: 'flex', gap: '10px', alignItems: 'flex-start'
    });
    this._el.innerHTML = `<span style="flex-shrink:0;font-size:14px">${icons[type]}</span><span>${message}</span>`;
    if (duration > 0) {
      this._timer = setTimeout(() => { if (this._el) this._el.style.display = 'none'; }, duration);
    }
  },

  hide() {
    if (this._el) this._el.style.display = 'none';
    clearTimeout(this._timer);
  },
};