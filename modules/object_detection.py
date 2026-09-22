"""
Object Detection Module for SecureExam — YOLOv8 with custom-trained weights.

Detects exam-relevant objects using the YOLOv8n model fine-tuned on the
Online-Exam-Proctoring dataset (5 classes: phone, extra_person, book,
laptop, student), mAP@0.5 = 0.978 on the validation set.

API matches what `app.py /api/proctor/frame` calls:
    object_detection_module.detect(frame_b64) -> list of suspicious labels

Back-compatible methods (analyze_frame_for_alerts etc.) are preserved so
decision_engine.py and any other consumer keeps working unchanged.

Fixes vs previous version:
  1. Per-class minimum bounding-box area filter — discards tiny detections
     caused by texture/pattern false positives (especially books).
  2. Per-class confidence floor — books require 0.75 confidence (on top of
     the global 0.55 threshold) because they visually overlap with many
     surfaces.
  3. Temporal smoothing in analyze_frame_for_alerts — a class is only
     reported positive after N consecutive confirmed frames, so a single
     bad frame no longer fires the decision engine.

Drop-in instructions:
    1. Overwrite modules/object_detection.py with this file.
    2. Place 'best_openvino_model/' (preferred) or 'best.pt' in the
       project root next to app.py.
    3. Uncomment the import in app.py (see app.py patch).
"""

import os
import cv2
import base64
import logging
import numpy as np
from io import BytesIO
from PIL import Image
from typing import List, Dict, Optional, Union

from ultralytics import YOLO

logger = logging.getLogger(__name__)


def _decode_frame(image_data: Union[str, np.ndarray]) -> Optional[np.ndarray]:
    """
    Robustly decode anything the Flask route or modules may pass:
      - raw base64 string (what exam.js sends after .split(',')[1])
      - 'data:image/...;base64,...' data URL
      - a file path
      - already-decoded numpy array
    Always returns BGR uint8 ndarray, or None on failure.
    """
    if isinstance(image_data, np.ndarray):
        return image_data
    if not isinstance(image_data, str):
        return None
    try:
        if image_data.startswith('data:image'):
            b64 = image_data.split(',', 1)[1]
            pil = Image.open(BytesIO(base64.b64decode(b64))).convert('RGB')
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        # Heuristic: long strings are base64 frames; short strings are file paths
        if len(image_data) > 200 and not os.path.exists(image_data):
            pil = Image.open(BytesIO(base64.b64decode(image_data))).convert('RGB')
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        return cv2.imread(image_data)
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        return None


class ObjectDetectionModule:
    """YOLOv8-based object detection for exam proctoring."""

    SUSPICIOUS_CLASSES = {'phone', 'book', 'extra_person'}
    BENIGN_CLASSES     = {'laptop', 'student'}

    DEFAULT_OPENVINO = 'best_openvino_model'
    DEFAULT_PT       = 'best.pt'

    def __init__(self, model_path: Optional[str] = None,
                 confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold

        # Minimum bounding-box area (px²) below which detections are discarded.
        # Books need a larger minimum to rule out texture / pattern matches.
        self.min_area: Dict[str, int] = {
            'book':         6000,   # ~77×77 px — must be clearly on the desk
            'phone':        2000,   # ~45×45 px
            'extra_person': 4000,   # ~63×63 px
        }
        self.default_min_area = 1500

        # Per-class confidence floor applied AFTER the global threshold.
        # Books are visually ambiguous (notebooks, folders, patterned cloth)
        # so we require a much higher score before reporting them.
        self.class_confidence: Dict[str, float] = {
            'book':         0.75,
            'phone':        0.55,
            'extra_person': 0.60,
        }

        # Temporal smoothing: how many consecutive confirmed frames are needed
        # before analyze_frame_for_alerts reports a class as present.
        # Resets to 0 on the first frame where the class is absent.
        self.confirm_frames: Dict[str, int] = {
            'book':         3,
            'phone':        2,
            'extra_person': 2,
        }
        self.default_confirm = 2
        # { label: consecutive_hit_count }
        self._consecutive: Dict[str, int] = {}

        if model_path is None:
            if os.path.isdir(self.DEFAULT_OPENVINO):
                model_path = self.DEFAULT_OPENVINO
            elif os.path.exists(self.DEFAULT_PT):
                model_path = self.DEFAULT_PT
            else:
                raise FileNotFoundError(
                    f"No model found. Expected '{self.DEFAULT_OPENVINO}/' "
                    f"or '{self.DEFAULT_PT}' in project root."
                )
        logger.info(f"Loading object detection model: {model_path}")
        self.model = YOLO(model_path)
        self.class_names = self.model.names
        logger.info(f"Loaded. Classes: {list(self.class_names.values())}")

    # ----------------------------------------------------------------- helpers

    def _filter(self, det: Dict) -> bool:
        """
        Return True if a detection passes both the per-class confidence floor
        and the minimum bounding-box area check.
        Both must pass — a high-confidence tiny detection is still discarded.
        """
        label    = det['type']
        min_area = self.min_area.get(label, self.default_min_area)
        min_conf = self.class_confidence.get(label, self.confidence_threshold)
        passes   = det['area'] >= min_area and det['confidence'] >= min_conf
        if not passes:
            logger.debug(
                f"Filtered out '{label}' conf={det['confidence']:.2f} "
                f"area={det['area']} (min_conf={min_conf}, min_area={min_area})"
            )
        return passes

    def _update_consecutive(self, label: str, detected: bool) -> bool:
        """
        Update the consecutive-hit counter for a label.
        Returns True only once the counter reaches confirm_frames[label].
        Resets to 0 on any frame where the label is absent.
        """
        if detected:
            self._consecutive[label] = self._consecutive.get(label, 0) + 1
        else:
            self._consecutive[label] = 0
        needed = self.confirm_frames.get(label, self.default_confirm)
        return self._consecutive.get(label, 0) >= needed

    def _run_yolo(self, image_data) -> List[Dict]:
        try:
            img = _decode_frame(image_data)
            if img is None:
                return []
            results = self.model(img, verbose=False, conf=self.confidence_threshold)
            detections = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    label  = self.class_names.get(cls_id, f'class_{cls_id}')
                    xyxy   = box.xyxy[0].cpu().numpy().astype(int).tolist()
                    x1, y1, x2, y2 = xyxy
                    detections.append({
                        'type':       label,
                        'bbox':       [x1, y1, x2 - x1, y2 - y1],
                        'confidence': float(box.conf[0]),
                        'area':       (x2 - x1) * (y2 - y1),
                    })
            # Apply per-class confidence floor + minimum area filter
            return [d for d in detections if self._filter(d)]
        except Exception as e:
            logger.error(f"YOLO inference error: {e}", exc_info=True)
            return []

    # ===== PRIMARY API expected by /api/proctor/frame in app.py =====

    def detect(self, image_data) -> List[str]:
        """
        Returns a list of suspicious label strings found in the frame.
        The route does `if 'phone' in objects: ...` etc.

        Note: 'extra_person' is exposed as 'person' to match the key the
        route's commented code uses. All other class names pass through.

        No temporal smoothing here — detect() is stateless and used for
        single-frame queries. Use analyze_frame_for_alerts() for the main
        proctoring loop (it applies consecutive-frame smoothing).
        """
        labels: List[str] = []
        for d in self._run_yolo(image_data):
            t = d['type']
            if t == 'extra_person':
                labels.append('person')
            elif t in self.SUSPICIOUS_CLASSES:
                labels.append(t)
        return labels

    # ===== Back-compat methods (preserved exact signatures) =====

    def detect_objects(self, image_data) -> List[Dict]:
        return self._run_yolo(image_data)

    def detect_suspicious_objects(self, image_data) -> List[Dict]:
        return [d for d in self._run_yolo(image_data)
                if d['type'] in self.SUSPICIOUS_CLASSES]

    def detect_multiple_people(self, image_data) -> bool:
        det = self._run_yolo(image_data)
        if any(d['type'] == 'extra_person' for d in det):
            return True
        return sum(1 for d in det if d['type'] == 'student') > 1

    def detect_mobile_phone(self, image_data) -> bool:
        return any(d['type'] == 'phone' for d in self._run_yolo(image_data))

    def detect_book(self, image_data) -> bool:
        return any(d['type'] == 'book' for d in self._run_yolo(image_data))

    def detect_external_monitor(self, image_data) -> bool:
        return False   # not a class in this model

    def detect_unusual_hands(self, image_data) -> bool:
        return False   # not a class in this model

    def analyze_frame_for_alerts(self, image_data) -> Dict:
        """
        Main proctoring loop entry point.

        Applies temporal smoothing: each suspicious class is only reported
        True after it appears in N consecutive frames (see confirm_frames).
        A single bad frame or texture false positive resets the counter and
        is never surfaced to the decision engine.
        """
        det = self._run_yolo(image_data)

        raw_book   = any(d['type'] == 'book'         for d in det)
        raw_phone  = any(d['type'] == 'phone'         for d in det)
        raw_person = any(d['type'] == 'extra_person'  for d in det)

        confirmed_book   = self._update_consecutive('book',         raw_book)
        confirmed_phone  = self._update_consecutive('phone',        raw_phone)
        confirmed_person = self._update_consecutive('extra_person', raw_person)

        logger.debug(
            f"ObjDet raw=book:{raw_book} phone:{raw_phone} person:{raw_person} | "
            f"confirmed=book:{confirmed_book} phone:{confirmed_phone} person:{confirmed_person} | "
            f"counters={self._consecutive}"
        )

        return {
            'suspicious_objects': [d for d in det
                                   if d['type'] in self.SUSPICIOUS_CLASSES],
            'multiple_people':    confirmed_person,
            'external_monitor':   False,
            'mobile_phone':       confirmed_phone,
            'book':               confirmed_book,
            'unusual_hands':      False,
            'all_detections':     det,
        }