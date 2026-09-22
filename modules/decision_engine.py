"""
SecureExam – Decision Engine  (Module 4)
=========================================
Implements the time-decay cheating score defined in Section 3.4:

    score(t) = max(0, score(t-dt_decay) - DECAY * dt_decay) + Σ WEIGHT_i * trigger_i * dt_add

Key fix over v1:
  dt is split into two separate intervals:
    dt_decay  – full elapsed time (capped 10 s) used only for score erosion
    dt_add    – capped at ADD_CAP (0.1 s) used for score accumulation
  This prevents frame-rate jitter and idle-resume spikes from inflating scores.

States
------
  NORMAL      score  <  50
  SUSPICIOUS  50  ≤  score  < 100
  ALERT            score  ≥ 100   → event logged, 3-second cooldown before next log

Event weights (points / second)
--------------------------------
  phone_detected      100   confidence-weighted, fast escalation
  extra_person         80   confidence-weighted
  book_detected        60   confidence-weighted
  head_turned          30   accumulates over time
  gaze_off             30   accumulates over time
  mouth_moving         20   accumulates over time
  no_face              15   accumulates over time
  face_mismatch       200   immediate escalation (not confidence-weighted – binary)

Integration point
-----------------
  _persist_event()  ← single clearly-marked method – swap in real DB call here.
"""

import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Tuneable constants ──────────────────────────────────────────────────────
DECAY          = 5.0    # points/second eroded when nothing is wrong
ALERT_COOLDOWN = 3.0    # seconds between consecutive ALERT log events
ADD_CAP        = 0.5    # seconds – max dt for score accumulation (caps idle-resume spikes)
ADD_MIN        = 0.033  # seconds – min dt for score accumulation (keeps scores meaningful at low fps)
DECAY_CAP      = 10.0   # seconds – max dt used for score *decay*  (prevents huge erasure)

THRESHOLD_SUSPICIOUS = 50.0
THRESHOLD_ALERT      = 100.0

# Weight table: points per second of continuous trigger
WEIGHTS: Dict[str, float] = {
    'phone_detected': 100.0,
    'extra_person':    80.0,
    'book_detected':   60.0,
    'head_turned':     30.0,
    'gaze_off':        30.0,
    'mouth_moving':    20.0,
    'no_face':         15.0,
    'face_mismatch':  200.0,   # binary – not confidence-weighted
}

# Which triggers carry YOLO confidence (multiplied into weight)
CONFIDENCE_WEIGHTED = {'phone_detected', 'extra_person', 'book_detected'}


def _conf(val) -> float:
    """
    Safely extract a 0-1 confidence value from a detection result.

    Handles three cases:
      bool  True / False  → 1.0 / (caller already guards falsy, but be safe)
      float / int         → clamped to [0.0, 1.0]
      anything else       → 1.0 (safe default)
    """
    if isinstance(val, bool):
        return 1.0
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return 1.0


class DecisionEngine:
    """
    Per-student time-decay cheating scorer.

    One instance is shared for the whole server process.  Each student is
    tracked by their string student_id; state is held in plain dicts so the
    engine works whether or not a database is available.
    """

    def __init__(self):
        # { student_id: float }  – current cheating score
        self._scores:          Dict[str, float] = {}
        # { student_id: float }  – wall-clock time of last update (time.monotonic)
        self._last_update:     Dict[str, float] = {}
        # { student_id: float }  – wall-clock time of last ALERT event logged
        self._last_alert_time: Dict[str, float] = {}
        # { student_id: list }   – in-memory event log (cleared on exam end)
        self._event_log:       Dict[str, list]  = {}

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def update(
        self,
        student_id:  str,
        face_result: Optional[Dict] = None,
        gaze_result: Optional[Dict] = None,
        obj_result:  Optional[Dict] = None,
    ) -> Dict:
        """
        Process one frame worth of module outputs and return the updated
        scoring decision.

        Parameters
        ----------
        student_id  : str
            The student's DB primary-key (as a string).
        face_result : dict | None
            Output from FaceRecognitionModule.verify():
            { 'matched': bool, 'distance': float }
            Pass None if face module did not run this frame.
        gaze_result : dict | None
            Output from GazeDetectionModule.analyze():
            Keys (any of these may be absent / False):
              'gaze_off_screen', 'gaze off screen',
              'head_turned',     'head turned',
              'mouth_moving',    'mouth moving',
              'face_detected'    (bool, default True if key absent)
        obj_result  : dict | None
            Output from ObjectDetectionModule.analyze_frame_for_alerts():
            Keys: 'mobile_phone', 'multiple_people', 'book'
            Values: bool  OR  float confidence (0-1)

        Returns
        -------
        dict with keys:
            score       float  – current cheating score
            state       str    – 'NORMAL' | 'SUSPICIOUS' | 'ALERT'
            triggers    list   – active trigger names this frame
            alert_fired bool   – True if an ALERT event was logged this frame
        """
        now      = time.monotonic()
        dt_decay = self._dt_decay(student_id, now)
        dt_add   = self._dt_add(student_id, now)

        # ── 1. Collect active triggers & effective weights ───────────────
        triggers:    List[str] = []
        weight_sum = 0.0

        # Face recognition
        # Only fire face_mismatch when a face IS present but IS NOT the student.
        # reason='no_face' → handled by gaze module's no_face trigger (15 pts).
        # reason='decode_failed' / 'not_enrolled' → do not penalise.
        if face_result is not None:
            if face_result.get('reason') == 'mismatch':
                triggers.append('face_mismatch')
                weight_sum += WEIGHTS['face_mismatch']   # binary – not conf-weighted

        # Gaze / behaviour
        if gaze_result is not None:
            if not gaze_result.get('face_detected', True):
                triggers.append('no_face')
                weight_sum += WEIGHTS['no_face']

            if (gaze_result.get('gaze_off_screen') or
                    gaze_result.get('gaze off screen')):
                triggers.append('gaze_off')
                weight_sum += WEIGHTS['gaze_off']

            if (gaze_result.get('head_turned') or
                    gaze_result.get('head turned')):
                triggers.append('head_turned')
                weight_sum += WEIGHTS['head_turned']

            if (gaze_result.get('mouth_moving') or
                    gaze_result.get('mouth moving')):
                triggers.append('mouth_moving')
                weight_sum += WEIGHTS['mouth_moving']

        # Object detection (confidence-weighted where available)
        if obj_result is not None:
            phone_val = obj_result.get('mobile_phone', False)
            if phone_val:
                triggers.append('phone_detected')
                weight_sum += WEIGHTS['phone_detected'] * _conf(phone_val)

            person_val = obj_result.get('multiple_people', False)
            if person_val:
                triggers.append('extra_person')
                weight_sum += WEIGHTS['extra_person'] * _conf(person_val)

            book_val = obj_result.get('book', False)
            if book_val:
                triggers.append('book_detected')
                weight_sum += WEIGHTS['book_detected'] * _conf(book_val)

        # ── 2. Apply time-decay formula (split dt) ───────────────────────
        #
        #   dt_decay  – full elapsed interval, used only for erosion.
        #               Large when frames are slow/idle, but that's fine:
        #               it just means the score decays faster during idle.
        #
        #   dt_add    – clamped between ADD_MIN and ADD_CAP.  The floor keeps
        #               scores meaningful at low fps; the ceiling prevents
        #               idle-resume spikes from inflating the score.
        #
        prev_score = self._scores.get(student_id, 0.0)
        new_score  = max(0.0, prev_score - DECAY * dt_decay) + weight_sum * dt_add
        self._scores[student_id]      = new_score
        self._last_update[student_id] = now

        # ── 3. Determine state ───────────────────────────────────────────
        if new_score >= THRESHOLD_ALERT:
            state = 'ALERT'
        elif new_score >= THRESHOLD_SUSPICIOUS:
            state = 'SUSPICIOUS'
        else:
            state = 'NORMAL'

        # ── 4. Log event on ALERT (with cooldown) ────────────────────────
        alert_fired = False
        if state == 'ALERT':
            last_alert = self._last_alert_time.get(student_id, 0.0)
            if (now - last_alert) >= ALERT_COOLDOWN:
                self._last_alert_time[student_id] = now
                event = {
                    'student_id': student_id,
                    'score':      round(new_score, 2),
                    'state':      state,
                    'triggers':   triggers,
                    'timestamp':  time.time(),   # wall-clock epoch for DB
                }
                self._persist_event(event)
                alert_fired = True
                logger.warning(
                    '[DecisionEngine] ALERT student=%s score=%.1f triggers=%s',
                    student_id, new_score, triggers
                )

        logger.debug(
            '[DecisionEngine] student=%s dt_decay=%.3f dt_add=%.3f '
            'score %.1f→%.1f state=%s triggers=%s',
            student_id, dt_decay, dt_add, prev_score, new_score, state, triggers
        )

        return {
            'score':       round(new_score, 1),
            'state':       state,
            'triggers':    triggers,
            'alert_fired': alert_fired,
        }

    def get_score(self, student_id: str) -> float:
        """Return the current (possibly stale) cheating score."""
        return round(self._scores.get(student_id, 0.0), 1)

    def get_state(self, student_id: str) -> str:
        score = self._scores.get(student_id, 0.0)
        if score >= THRESHOLD_ALERT:
            return 'ALERT'
        if score >= THRESHOLD_SUSPICIOUS:
            return 'SUSPICIOUS'
        return 'NORMAL'

    def reset(self, student_id: str) -> None:
        """Clear all state for a student (call when exam ends)."""
        for d in (self._scores, self._last_update,
                  self._last_alert_time, self._event_log):
            d.pop(student_id, None)

    def get_event_log(self, student_id: str) -> List[Dict]:
        """Return in-memory event log for this student."""
        return list(self._event_log.get(student_id, []))

    # ── Legacy / compatibility shim ──────────────────────────────────────
    # app.py v1 called evaluate_proctoring_data(); keep it working.

    def evaluate_proctoring_data(self, proctoring_data: Dict) -> Dict:
        """
        Compatibility wrapper used by older app.py versions.
        Maps the old dict-based interface to update().
        """
        student_id = str(proctoring_data.get('student_id', 'unknown'))

        face_result = None
        if 'face_detected' in proctoring_data:
            face_result = {'matched': proctoring_data['face_detected']}

        gaze_result = proctoring_data.get('gaze_metrics') or {}
        # also accept flat keys
        for k in ('gaze_off_screen', 'head_turned', 'mouth_moving', 'face_detected'):
            if k in proctoring_data:
                gaze_result[k] = proctoring_data[k]

        obj_alerts = proctoring_data.get('object_alerts') or {}
        obj_result: Dict = {
            'mobile_phone':    obj_alerts.get('mobile_phone', False),
            'multiple_people': obj_alerts.get('multiple_people', False),
            'book':            obj_alerts.get('book', False),
        }

        decision = self.update(student_id, face_result, gaze_result, obj_result)

        # Return shape that old callers expected
        return {
            'alerts': [
                {
                    'type':     t,
                    'severity': 'critical' if decision['score'] >= THRESHOLD_ALERT else 'warning',
                    'message':  t,
                }
                for t in decision['triggers']
            ],
            'violation_score': decision['score'],
            'action':          self._score_to_action(decision['score']),
            'state':           decision['state'],
            'timestamp':       time.time(),
        }

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _dt_decay(self, student_id: str, now: float) -> float:
        """
        Seconds to use for score *erosion*.
        Full elapsed time, capped at DECAY_CAP to prevent wiping the score
        after very long idle periods.
        Returns 0.0 on the first frame (no prior timestamp).
        """
        last = self._last_update.get(student_id)
        if last is None:
            return 0.0
        return min(now - last, DECAY_CAP)

    def _dt_add(self, student_id: str, now: float) -> float:
        """
        Seconds to use for score *accumulation*.
        Clamped between ADD_MIN and ADD_CAP:
          ADD_MIN (0.033 s) guarantees meaningful accumulation even at low
          frame rates (e.g. 2 fps) so scores rise at the intended rate.
          ADD_CAP (0.5 s) prevents idle-resume spikes from inflating the
          score when a large gap occurs between frames.
        Returns 0.0 on the first frame (record timestamp, accumulate nothing).
        """
        last = self._last_update.get(student_id)
        if last is None:
            return 0.0
        elapsed = now - last
        return max(ADD_MIN, min(elapsed, ADD_CAP))

    def _persist_event(self, event: Dict) -> None:
        """
        ══════════════════════════════════════════════════════════════════
        INTEGRATION POINT – replace body with your DB insert when ready.
        ══════════════════════════════════════════════════════════════════
        Currently stores in memory so the engine works standalone.
        """
        sid = event['student_id']
        if sid not in self._event_log:
            self._event_log[sid] = []
        self._event_log[sid].append(event)
        logger.info('[DecisionEngine] event persisted: %s', event)

    @staticmethod
    def _score_to_action(score: float) -> str:
        if score >= THRESHOLD_ALERT:
            return 'block'
        if score >= THRESHOLD_SUSPICIOUS:
            return 'flag'
        if score >= 25:
            return 'warn'
        return 'none'