/* ═══════════════════════════════════════════════════════════
   enrollment.js — Face Enrollment
   Paste into: static/js/enrollment.js
   Load on: enroll.html  (after api.js)

   ── From yours: retakePhoto(), step indicator updates,
                  proper stopWebcam on page unload
   ── From mine:  3-photo strip UI, scan line, meter updates,
                  IIFE module pattern, direct API.enroll calls
═══════════════════════════════════════════════════════════ */

const Enroll = (() => {

  // ── STATE ─────────────────────────────────────────────
  const state = {
    stream:      null,
    photoCount:  0,
    capturedFrames: [],   // base64 strings for each captured photo
    TOTAL:       3,
  };

  // ── DOM REFS ───────────────────────────────────────────
  let els = {};

  // ── INIT ──────────────────────────────────────────────
  function init() {
    els = {
      video:   document.getElementById('enroll-video'),
      hint:    document.getElementById('enroll-hint'),
      scan:    document.getElementById('enroll-scan'),
      action:  document.getElementById('enroll-action'),
      mLight:  document.getElementById('m-light'),
      mFace:   document.getElementById('m-face'),
      mPos:    document.getElementById('m-pos'),
      thumbs:  [0, 1, 2].map(i => document.getElementById('t' + i)),
    };
    _renderActionBtn();

    // Stop camera when user navigates away
    window.addEventListener('beforeunload', stopCamera);
  }

  // ── CAMERA ────────────────────────────────────────────
  async function startCamera() {
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      });
      els.video.srcObject = state.stream;
      els.hint.textContent = '✓ Camera active — align face inside the oval';
      if (els.scan) els.scan.style.display = 'block';
      if (els.mPos) els.mPos.className = 'meter ok';
      _renderActionBtn();
    } catch (err) {
      console.error('[Enroll] Camera error:', err);
      if (els.hint) els.hint.textContent = '⚠ Camera access denied';
      if (els.mFace) els.mFace.className = 'meter bad';
      if (els.action) els.action.innerHTML = `
        <div class="alert alert-danger">
          <span class="alert-icon">⚠</span>
          <div>Camera access was denied. Please allow camera access in your browser settings and refresh the page.</div>
        </div>`;
    }
  }

  function stopCamera() {
    if (state.stream) {
      state.stream.getTracks().forEach(t => t.stop());
      state.stream = null;
    }
    if (els.scan) els.scan.style.display = 'none';
  }

  // ── CAPTURE ───────────────────────────────────────────
  function capturePhoto() {
    if (state.photoCount >= state.TOTAL || !state.stream) return;

    // Grab frame from video into canvas
    const canvas = document.createElement('canvas');
    canvas.width  = els.video.videoWidth  || 640;
    canvas.height = els.video.videoHeight || 480;
    canvas.getContext('2d').drawImage(els.video, 0, 0);
    const frameBase64 = canvas.toDataURL('image/jpeg', 0.85);
    state.capturedFrames.push(frameBase64);

    // Update thumbnail
    const thumb = els.thumbs[state.photoCount];
    if (thumb) {
      thumb.className = 'thumb done';
      const img = document.createElement('img');
      img.src = frameBase64;
      img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:8px';
      thumb.innerHTML = '';
      thumb.appendChild(img);
      const tick = document.createElement('div');
      tick.className = 'tick'; tick.textContent = '✓';
      thumb.appendChild(tick);
    }

    state.photoCount++;
    if (els.hint) els.hint.textContent = `✓ Photo ${state.photoCount} of ${state.TOTAL} captured`;

    API.enroll.capture(frameBase64, state.photoCount - 1)
      .catch(err => Toast.show('error', 'Failed to save photo. Retake?'));

    if (state.photoCount === state.TOTAL) {
      _onAllCaptured();
    } else {
      _renderActionBtn();
    }
  }

  // ── RETAKE  (from your system — important UX) ─────────
  function retakePhoto() {
    state.photoCount = 0;
    state.capturedFrames = [];

    // Reset all thumbnails
    els.thumbs.forEach(t => {
      if (t) { t.className = 'thumb'; t.innerHTML = '📷'; }
    });

    if (els.hint) els.hint.textContent = '✓ Camera active — align face inside the oval';
    _renderActionBtn();
    Toast.show('info', 'Photos cleared. Capture 3 new photos.');
  }

  // ── SUBMIT ENROLLMENT ─────────────────────────────────
  async function submitEnrollment() {
    if (state.capturedFrames.length < state.TOTAL) {
      Toast.show('warning', 'Please capture all 3 photos first.');
      return;
    }

    Toast.show('info', 'Saving your biometric profile...', 0);

    try {
      await API.enroll.confirm();
      Toast.show('success', 'Enrollment complete! Redirecting...');
      setTimeout(() => { window.location.href = '/waiting'; }, 1800);
    } catch (err) {
      Toast.show('error', 'Enrollment failed. Please try again.');
      console.error('[Enroll] Submit error:', err);
    }
  }

  // ── UPDATE STEP INDICATOR (from your system) ──────────
  function _updateStep(stepNumber) {
    document.querySelectorAll('.step-h').forEach((step, idx) => {
      step.classList.remove('active', 'done');
      if (idx + 1 < stepNumber)  step.classList.add('done');
      if (idx + 1 === stepNumber) step.classList.add('active');
    });
  }

  // ── INTERNAL HELPERS ──────────────────────────────────
  function _onAllCaptured() {
    stopCamera();
    _updateStep(3); // advance to step 3 (verification)

    if (els.action) {
      els.action.innerHTML = `
        <div class="alert alert-success" style="margin-bottom:12px">
          <span class="alert-icon">✓</span>
          <div><strong>All 3 photos captured.</strong> Your biometric profile is ready.</div>
        </div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-secondary btn-auto" onclick="Enroll.retakePhoto()" style="flex:1">
            ↺ Retake
          </button>
          <button class="btn btn-primary btn-auto" onclick="Enroll.submitEnrollment()" style="flex:2">
            Continue →
          </button>
        </div>`;
    }
  }

  function _renderActionBtn() {
    if (!els.action) return;
    if (!state.stream) {
      els.action.innerHTML = `
        <button class="btn btn-primary" onclick="Enroll.startCamera()">
          Start Camera
        </button>`;
    } else {
      els.action.innerHTML = `
        <button class="btn btn-primary" onclick="Enroll.capturePhoto()">
          📷 Capture Photo ${state.photoCount + 1} of ${state.TOTAL}
        </button>`;
    }
  }

  // ── PUBLIC API ────────────────────────────────────────
  return { init, startCamera, capturePhoto, retakePhoto, submitEnrollment };

})();

document.addEventListener('DOMContentLoaded', Enroll.init);
