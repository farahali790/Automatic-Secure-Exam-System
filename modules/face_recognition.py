"""
Face Recognition Module for SecureExam — `face_recognition` (dlib) ResNet
128-d embeddings.

Provides the API that `app.py` expects:
    extract_encoding(frame_b64)             -> 128-d list or None
    get_average_encoding(student_id)        -> averaged encoding from
                                                3 enrollment captures
    verify(frame_b64, stored_encoding)      -> {'matched': bool, ...}

Back-compatible methods (extract_face_encoding, enroll_student, verify_face,
detect_faces, etc.) are preserved.

Fixes vs previous version:
  1. Always converts to 3-channel RGB before encoding, so PNG enrollment
     photos with alpha channels don't crash dlib.
  2. Accepts raw base64 (what exam.js sends) AND data URLs AND file paths.
  3. verify() returns matched=True with reason='no_face' when no face is
     detected — absence is NOT treated as a mismatch (weight 200) but
     instead left to the gaze module's no_face trigger (weight 15).
  4. extract_encoding() rejects blurry enrollment frames (Laplacian < 80)
     so poor-quality captures don't skew the averaged stored encoding.
"""

import os
import cv2
import json
import base64
import logging
import numpy as np
from io import BytesIO
from PIL import Image
from typing import Optional, Tuple, List, Dict, Union

import face_recognition as fr

logger = logging.getLogger(__name__)


def _decode_to_rgb(image_data) -> Optional[np.ndarray]:
    """
    Decode to a 3-channel RGB ndarray (what face_recognition / dlib expects).
    Accepts raw base64, data URLs, file paths, or already-decoded arrays.
    """
    try:
        if isinstance(image_data, np.ndarray):
            arr = image_data
            if arr.ndim == 2:
                return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
            if arr.shape[2] == 4:
                return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
            # Assume BGR (OpenCV convention); convert to RGB
            return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)

        if not isinstance(image_data, str):
            return None

        if image_data.startswith('data:image'):
            b64 = image_data.split(',', 1)[1]
            pil = Image.open(BytesIO(base64.b64decode(b64))).convert('RGB')
            return np.array(pil)

        if len(image_data) > 200 and not os.path.exists(image_data):
            pil = Image.open(BytesIO(base64.b64decode(image_data))).convert('RGB')
            return np.array(pil)

        # File path
        bgr = cv2.imread(image_data)
        if bgr is None:
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        return None


class FaceRecognitionModule:
    """128-d face embedding-based identity verification."""

    def __init__(self, model: str = 'hog', tolerance: float = 0.55):
        """
        Args:
            model: 'hog' (CPU, default) or 'cnn' (GPU dlib, more accurate)
            tolerance: lower = stricter. 0.55 intentionally strict for
                anti-impersonation in an exam context.
        """
        self.model = model
        self.tolerance = tolerance
        # Per-student temp storage during 3-photo enrollment (keyed by
        # student_id -> {index: encoding}). Cleared on get_average_encoding.
        self._enrollment_buffer: Dict[str, Dict[int, np.ndarray]] = {}
        # In-process cache (also rebuilt from DB at startup if needed)
        self.known_face_encodings: List[np.ndarray] = []
        self.known_face_names: List[str] = []

    # ----------------------------------------------------------------- helpers
    def _encode_largest_face(self, rgb: np.ndarray) -> Optional[np.ndarray]:
        """Find faces, return encoding of the largest (closest-to-camera) one."""
        rgb = np.ascontiguousarray(rgb, dtype=np.uint8)   # numpy 2.x / dlib compat
        locs = fr.face_locations(rgb, model=self.model)
        if not locs:
            return None
        largest = max(locs, key=lambda L: (L[2] - L[0]) * (L[1] - L[3]))
        encs = fr.face_encodings(rgb, [largest])
        return encs[0] if encs else None

    # ================ PRIMARY API expected by app.py ====================

    def extract_encoding(self, image_data, student_id: Optional[str] = None,
                         index: Optional[int] = None) -> Optional[list]:
        """
        Compute the 128-d face encoding for one frame.

        If student_id and index are provided, the encoding is buffered
        for that student under that index (0/1/2) — used by the 3-photo
        enrollment flow.

        Blurry frames (Laplacian variance < 80) are rejected before
        buffering so poor captures don't skew the averaged enrollment
        encoding and cause false mismatches during the exam.

        Returns:
            list (128 floats) on success, None if no face or frame rejected.
        """
        rgb = _decode_to_rgb(image_data)
        if rgb is None:
            return None

        # Reject blurry enrollment frames before buffering
        if student_id is not None and index is not None:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_score < 80:
                logger.warning(
                    f"Enrollment frame too blurry (score={blur_score:.1f}), "
                    f"skipping (student={student_id}, index={index})"
                )
                return None

        enc = self._encode_largest_face(rgb)
        if enc is None:
            return None

        if student_id is not None and index is not None:
            self._enrollment_buffer.setdefault(student_id, {})[int(index)] = enc
            logger.info(f"Buffered enrollment encoding for {student_id} idx={index}")

        return enc.tolist()

    def get_average_encoding(self, student_id: str) -> Optional[list]:
        """
        Average all buffered enrollment encodings for this student.

        Call after the 3 enrollment captures complete. Returns None if no
        encodings were buffered. Clears the student's buffer after returning.
        """
        buf = self._enrollment_buffer.get(student_id, {})
        if not buf:
            logger.warning(f"No buffered encodings for {student_id}")
            return None
        encs = list(buf.values())
        avg = np.mean(np.stack(encs, axis=0), axis=0)
        del self._enrollment_buffer[student_id]
        logger.info(f"Averaged {len(encs)} encodings for {student_id}")
        return avg.tolist()

    def verify(self, image_data, stored_encoding) -> Dict:
        """
        Compare current frame against a stored encoding (from DB).

        Args:
            image_data: raw base64 / data URL / path / ndarray
            stored_encoding: list, tuple, or numpy array of 128 floats
                (typically json.loads(student.face_encoding))

        Returns:
            {'matched': bool, 'distance': float|None, 'reason': str}

        Reason values:
            'match'         – face found and distance <= tolerance
            'mismatch'      – face found but distance > tolerance (real alert)
            'no_face'       – no face detected this frame; matched=True so the
                              decision engine does NOT fire face_mismatch (200pts);
                              the gaze module's no_face trigger (15pts) handles it
            'decode_failed' – could not decode the image
            'not_enrolled'  – no stored encoding on file
        """
        if stored_encoding is None or len(stored_encoding) == 0:
            return {'matched': False, 'distance': None, 'reason': 'not_enrolled'}

        rgb = _decode_to_rgb(image_data)
        if rgb is None:
            return {'matched': False, 'distance': None, 'reason': 'decode_failed'}

        current = self._encode_largest_face(rgb)
        if current is None:
            # No face visible this frame — not a mismatch, just absence.
            # Return matched=True so the decision engine skips the 200-pt
            # face_mismatch trigger. The gaze module handles no_face (15 pts).
            return {'matched': True, 'distance': None, 'reason': 'no_face'}

        stored = np.asarray(stored_encoding, dtype=np.float64)
        distance = float(fr.face_distance([stored], current)[0])
        return {
            'matched':  distance <= self.tolerance,
            'distance': round(distance, 3),
            'reason':   'match' if distance <= self.tolerance else 'mismatch',
        }

    # ============== Back-compat methods (preserved shapes) ==============

    def extract_face_encoding(self, image_data) -> Optional[np.ndarray]:
        rgb = _decode_to_rgb(image_data)
        if rgb is None:
            return None
        return self._encode_largest_face(rgb)

    def enroll_student(self, student_id: str, image_data) -> bool:
        enc = self.extract_face_encoding(image_data)
        if enc is None:
            return False
        self.known_face_encodings.append(enc)
        self.known_face_names.append(student_id)
        return True

    def verify_face(self, image_data, student_id: str,
                    tolerance: float = 0.6) -> Tuple[bool, float]:
        current = self.extract_face_encoding(image_data)
        if current is None or student_id not in self.known_face_names:
            return False, 0.0
        idx = self.known_face_names.index(student_id)
        stored = self.known_face_encodings[idx]
        distance = float(fr.face_distance([stored], current)[0])
        return distance <= tolerance, float(1.0 - distance)

    def detect_faces(self, image_data) -> List[Tuple[int, int, int, int]]:
        rgb = _decode_to_rgb(image_data)
        if rgb is None:
            return []
        return fr.face_locations(rgb, model=self.model)

    def is_face_visible(self, image_data) -> bool:
        return len(self.detect_faces(image_data)) > 0

    def get_face_quality(self, image_data) -> float:
        rgb = _decode_to_rgb(image_data)
        if rgb is None:
            return 0.0
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return float(min(1.0, variance / 500.0))