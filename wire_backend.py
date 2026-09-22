# Wire up the three commented-out backend calls so JWT auth and persistence actually work.

# ============== PATCH 1: student_login.html ==============
p = 'templates/student_login.html'
s = open(p, encoding='utf-8').read()
old = """    // ── Production: uncomment to call backend ──
    // API.auth.login(sid, pass)
    //   .then(() => { window.location.href = '/enroll'; })
    //   .catch(err => {
    //     Toast.show('error', err.data?.message || 'Login failed.');
    //     btn.disabled = false; btn.textContent = 'Continue →';
    //   });

    // ── Demo: go straight to enroll ──
    window.location.href = '/enroll';"""
new = """    API.auth.login(sid, pass)
      .then(() => { window.location.href = '/enroll'; })
      .catch(err => {
        Toast.show('error', err.data?.message || 'Login failed.');
        btn.disabled = false; btn.textContent = 'Continue →';
      });"""
if old in s:
    open(p, 'w', encoding='utf-8').write(s.replace(old, new))
    print('student_login.html: wired API.auth.login')
elif 'API.auth.login(sid' in s and '// API.auth.login' not in s:
    print('student_login.html: already wired')
else:
    print('student_login.html: PATTERN NOT FOUND — manual fix needed')

# ============== PATCH 2: enrollment.js — capture ==============
p = 'static/js/enrollment.js'
s = open(p, encoding='utf-8').read()

old_cap = """    // In production — send to backend immediately:
    // API.enroll.capture(frameBase64, state.photoCount - 1)
    //   .catch(err => Toast.show('error', 'Failed to save photo. Retake?'));"""
new_cap = """    API.enroll.capture(frameBase64, state.photoCount - 1)
      .catch(err => Toast.show('error', 'Failed to save photo. Retake?'));"""
if old_cap in s:
    s = s.replace(old_cap, new_cap)
    print('enrollment.js: wired API.enroll.capture')
elif 'API.enroll.capture(' in s and '// API.enroll.capture' not in s:
    print('enrollment.js: capture already wired')
else:
    print('enrollment.js: CAPTURE PATTERN NOT FOUND')

# ============== PATCH 3: enrollment.js — confirm ==============
old_conf = """      // In production: API.enroll.confirm() after all 3 captures
      // const result = await API.enroll.confirm();
      Toast.show('success', 'Enrollment complete! Redirecting...');"""
new_conf = """      await API.enroll.confirm();
      Toast.show('success', 'Enrollment complete! Redirecting...');"""
if old_conf in s:
    s = s.replace(old_conf, new_conf)
    print('enrollment.js: wired API.enroll.confirm')
elif 'await API.enroll.confirm()' in s and '// const result = await API.enroll.confirm' not in s:
    print('enrollment.js: confirm already wired')
else:
    print('enrollment.js: CONFIRM PATTERN NOT FOUND')

open(p, 'w', encoding='utf-8').write(s)

# ============== PATCH 4: invigilator_login.html ==============
p = 'templates/invigilator_login.html'
s = open(p, encoding='utf-8').read()
old_inv = """    // ── Production: uncomment to call backend ──
    // API.auth.invigLogin(
    //   document.getElementById('invig_email').value,
    //   document.getElementById('invig_password').value
    // ).then(() => { window.location.href = '/invigilator'; })
    //  .catch(err => {
    //    Toast.show('error', err.data?.message || 'Login failed.');
    //    btn.disabled = false; btn.textContent = 'Access Dashboard →';
    //  });

    // ── Demo: go straight to dashboard ──
    window.location.href = '/invigilator';"""
new_inv = """    API.auth.invigLogin(
      document.getElementById('invig_email').value,
      document.getElementById('invig_password').value
    ).then(() => { window.location.href = '/invigilator'; })
     .catch(err => {
       Toast.show('error', err.data?.message || 'Login failed.');
       btn.disabled = false; btn.textContent = 'Access Dashboard →';
     });"""
if old_inv in s:
    open(p, 'w', encoding='utf-8').write(s.replace(old_inv, new_inv))
    print('invigilator_login.html: wired API.auth.invigLogin')
elif 'API.auth.invigLogin(' in s and '// API.auth.invigLogin' not in s:
    print('invigilator_login.html: already wired')
else:
    print('invigilator_login.html: PATTERN NOT FOUND')

print('\nDone.')