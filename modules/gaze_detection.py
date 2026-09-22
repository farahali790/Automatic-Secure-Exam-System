"""
Gaze Detection Module for SecureExam — MediaPipe Tasks API.

Replaces the previous Haar-cascade implementation (which measured face
position, not actual gaze) with real behavioral analysis using MediaPipe
FaceLandmarker (478 landmarks including iris).

Detects three behavioral signals:
    - gaze_off_screen : iris off-center OR face missing
    - head_turned     : head yaw or pitch exceeds threshold (via 3D solvePnP)
    - mouth_moving    : mouth aspect ratio above threshold (talking)

API matches what `app.py /api/proctor/frame` calls:
    gaze_detection_module.analyze(frame_b64)
        -> {'gaze_off_screen': bool, 'head_turned': bool, 'mouth_moving': bool}

Back-compatible methods (detect_gaze, is_looking_at_screen, etc.) are
preserved.

Required file in project root:
    face_landmarker.task   (download URL in module docstring below)
"""

# Download the model once (run in project root):
#   wget https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

import os
import cv2
import base64
import logging
import numpy as np
from io import BytesIO
from PIL import Image
from typing import Dict, Optional, Union

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

logger = logging.getLogger(__name__)


def _decode_frame(image_data: Union[str, np.ndarray]) -> Optional[np.ndarray]:
    """Same robust decoder used across modules."""
    if isinstance(image_data, np.ndarray):
        return image_data
    if not isinstance(image_data, str):
        return None
    try:
        if image_data.startswith('data:image'):
            b64 = image_data.split(',', 1)[1]
            pil = Image.open(BytesIO(base64.b64decode(b64))).convert('RGB')
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        if len(image_data) > 200 and not os.path.exists(image_data):
            pil = Image.open(BytesIO(base64.b64decode(image_data))).convert('RGB')
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        return cv2.imread(image_data)
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        return None


class GazeDetectionModule:
    """MediaPipe-based behavioral analysis for exam proctoring."""

    DEFAULT_MODEL_PATH = 'face_landmarker.task'

    # Thresholds — tunable via constructor or class constants
    HEAD_YAW_THRESHOLD   = 30   # degrees (matches the README's "Head turned > 30°")
    HEAD_PITCH_THRESHOLD = 25
    GAZE_THRESHOLD       = 0.20
    MAR_THRESHOLD        = 0.30

    # MediaPipe FaceLandmarker indices (refine_landmarks=True equivalent)
    HEAD_POSE_INDICES = [1, 152, 33, 263, 61, 291]
    RIGHT_IRIS_CENTER, LEFT_IRIS_CENTER = 468, 473
    RIGHT_EYE_OUTER, RIGHT_EYE_INNER = 33, 133
    LEFT_EYE_OUTER, LEFT_EYE_INNER = 263, 362
    MOUTH_TOP, MOUTH_BOTTOM = 13, 14
    MOUTH_LEFT, MOUTH_RIGHT = 78, 308

    MODEL_POINTS_3D = np.array([
        (0.0, 0.0, 0.0), (0.0, -330.0, -65.0),
        (-225.0, 170.0, -135.0), (225.0, 170.0, -135.0),
        (-150.0, -150.0, -125.0), (150.0, -150.0, -125.0),
    ])

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"face_landmarker.task not found at '{model_path}'. "
                f"Download from "
                f"https://storage.googleapis.com/mediapipe-models/"
                f"face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            )
        base = mp_python.BaseOptions(model_asset_path=model_path)
        opts = mp_vision.FaceLandmarkerOptions(
            base_options=base, num_faces=1,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self.landmarker = mp_vision.FaceLandmarker.create_from_options(opts)
        logger.info(f"GazeDetectionModule ready (model: {model_path})")

    # ----- geometry helpers -----
    @staticmethod
    def _norm_angle(a):
        while a > 180:  a -= 360
        while a < -180: a += 360
        return a

    def _head_pose(self, lm, w, h):
        pts = np.array([[lm[i].x * w, lm[i].y * h]
                        for i in self.HEAD_POSE_INDICES], dtype="double")
        cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]],
                       dtype="double")
        ok, rvec, tvec = cv2.solvePnP(
            self.MODEL_POINTS_3D, pts, cam, np.zeros((4, 1)),
            flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            return 0.0, 0.0, 0.0
        rmat, _ = cv2.Rodrigues(rvec)
        euler = cv2.decomposeProjectionMatrix(np.hstack((rmat, tvec)))[6]
        pitch, yaw, roll = (self._norm_angle(float(a)) for a in euler.flatten())
        if pitch >  90: pitch = 180 - pitch
        if pitch < -90: pitch = -180 - pitch
        return pitch, yaw, roll

    def _gaze_ratios(self, lm):
        def r(iris, a, b):
            xi, xa, xb = lm[iris].x, lm[a].x, lm[b].x
            lo, hi = min(xa, xb), max(xa, xb)
            return (xi - lo) / (hi - lo + 1e-6)
        return (r(self.LEFT_IRIS_CENTER, self.LEFT_EYE_OUTER, self.LEFT_EYE_INNER),
                r(self.RIGHT_IRIS_CENTER, self.RIGHT_EYE_OUTER, self.RIGHT_EYE_INNER))

    def _mar(self, lm):
        t = np.array([lm[self.MOUTH_TOP].x,    lm[self.MOUTH_TOP].y])
        b = np.array([lm[self.MOUTH_BOTTOM].x, lm[self.MOUTH_BOTTOM].y])
        l = np.array([lm[self.MOUTH_LEFT].x,   lm[self.MOUTH_LEFT].y])
        r = np.array([lm[self.MOUTH_RIGHT].x,  lm[self.MOUTH_RIGHT].y])
        return np.linalg.norm(t - b) / (np.linalg.norm(l - r) + 1e-6)

    # ----- core processing (used by all public methods) -----
    def _process(self, image_data) -> Dict:
        """Run the landmark model and compute all signals + raw values."""
        frame = _decode_frame(image_data)
        out = {
            'face_detected': False,
            'gaze_off_screen': False,
            'head_turned':     False,
            'mouth_moving':    False,
            'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0,
            'mar': 0.0, 'gaze_left': 0.5, 'gaze_right': 0.5,
        }
        if frame is None:
            out['gaze_off_screen'] = True   # treat decode failure as off-screen
            return out

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.landmarker.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

        if not result.face_landmarks:
            out['gaze_off_screen'] = True   # no face = treat as off-screen
            return out

        lm = result.face_landmarks[0]
        out['face_detected'] = True

        pitch, yaw, roll = self._head_pose(lm, w, h)
        out['pitch'], out['yaw'], out['roll'] = pitch, yaw, roll
        if abs(yaw) > self.HEAD_YAW_THRESHOLD or abs(pitch) > self.HEAD_PITCH_THRESHOLD:
            out['head_turned'] = True

        gl, gr = self._gaze_ratios(lm)
        out['gaze_left'], out['gaze_right'] = gl, gr
        if abs((gl + gr) / 2 - 0.5) > self.GAZE_THRESHOLD:
            out['gaze_off_screen'] = True

        m = self._mar(lm)
        out['mar'] = m
        if m > self.MAR_THRESHOLD:
            out['mouth_moving'] = True

        return out

    # ===== PRIMARY API expected by /api/proctor/frame =====
    def analyze(self, image_data) -> Dict:
        """
        Returns exactly the three booleans the route's commented code uses.

        Example:
            gaze = gaze_detection_module.analyze(frame_b64)
            if gaze['gaze_off_screen']: ...
            if gaze['head_turned']:     ...
            if gaze['mouth_moving']:    ...
        """
        r = self._process(image_data)
        return {
            'gaze_off_screen': r['gaze_off_screen'],
            'head_turned':     r['head_turned'],
            'mouth_moving':    r['mouth_moving'],
        }

    # ===== Back-compat methods (preserved shapes for any other consumers) =====
    def detect_gaze(self, image_data) -> Dict:
        """Original API — returns {focused, confidence, gaze_direction, deviation_angle}."""
        r = self._process(image_data)
        if not r['face_detected']:
            return {'focused': False, 'confidence': 0.0,
                    'gaze_direction': 'not_detected', 'deviation_angle': 0}
        avg_gaze = (r['gaze_left'] + r['gaze_right']) / 2
        if abs(avg_gaze - 0.5) <= self.GAZE_THRESHOLD and not r['head_turned']:
            direction = 'forward'
            focused = True
        else:
            direction = 'left' if avg_gaze < 0.5 else 'right'
            focused = False
        deviation = float(abs(r['yaw']) + abs(r['pitch']))
        return {
            'focused': focused,
            'confidence': float(1.0 - abs(avg_gaze - 0.5) * 2),
            'gaze_direction': direction,
            'deviation_angle': deviation,
        }

    def is_looking_at_screen(self, image_data, threshold: float = 0.7) -> bool:
        m = self.detect_gaze(image_data)
        return m['focused'] and m['confidence'] >= threshold

    def get_gaze_direction(self, image_data) -> str:
        return self.detect_gaze(image_data)['gaze_direction']

    def detect_gaze_deviation(self, image_data, max_angle: float = 30) -> bool:
        return self.detect_gaze(image_data)['deviation_angle'] > max_angle