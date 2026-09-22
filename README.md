# 🎓 SecureExam — AI-Powered Online Exam Proctoring System

> **Graduation Project — British University in Egypt**  
> Faculty of Informatics and Computer Science — Software Engineering  
> **By:** Farah Ali Abuassi | **Supervisor:** Dr. Noura Elmaghawry | December 2025

A comprehensive web application for conducting secure, AI-monitored online exams with real-time proctoring using face recognition, gaze detection, and object detection — running entirely on CPU with no GPU required.

---

## 📊 Results at a Glance

| Metric | Value |
|--------|-------|
| Object Detection mAP@0.5 | **97.8%** |
| Precision | **95.6%** |
| Recall | **96.8%** |
| Inference speed (PyTorch) | 7.3 FPS |
| Inference speed (OpenVINO) | **12.0 FPS** (1.66× speedup) |
| Identity verification accuracy | No false accepts / rejects in test set |

---

## ✨ Features

### 🔒 Security & Proctoring
- **Face Recognition** — enrollment and continuous facial verification using dlib ResNet (128-dimensional embeddings)
- **Gaze Detection** — real-time eye tracking via MediaPipe FaceMesh (478 landmarks)
- **Object Detection** — YOLOv8n detects phones, books, and extra people, optimised with OpenVINO for 1.66× CPU speedup
- **Decision Engine** — rule-based scoring engine that combines all signals into a live cheating score with time-decay

### 👨‍🎓 Student Features
- Secure login and 3-photo biometric face enrollment
- Real-time exam interface with countdown timer
- Question navigation, flagging for review, difficulty badges
- Proctoring frame loop running every 4 seconds during exam

### 👁️ Invigilator Dashboard
- Real-time monitoring of all students with live risk scores
- Alert log with severity levels (critical / warning / info)
- Flag and block actions with confirmation
- Filter by status (all / active / flagged / completed)
- Search by name or student ID
- Slide-in alerts panel and session countdown timer
- Configurable proctoring thresholds (Settings tab)

---

## 📁 Project Structure

```
SecureExam/
├── static/
│   ├── css/
│   │   ├── main.css              # Shared design tokens, buttons, forms, camera components
│   │   ├── auth.css              # Landing, login, enrollment, waiting room
│   │   ├── exam.css              # Live exam interface + submitted page
│   │   └── dashboard.css         # Invigilator dashboard
│   ├── js/
│   │   ├── api.js                # APIClient class + Toast notifications
│   │   ├── enrollment.js         # Webcam capture, 3-photo strip, retake
│   │   ├── exam.js               # Timer, questions, answers, proctoring loop
│   │   └── dashboard.js          # Student tiles, alerts, tabs, auto-refresh
│   └── assets/
│       └── logo.svg
├── templates/
│   ├── landing.html              # Role selection + features section
│   ├── student_login.html        # Step 1 — student credentials
│   ├── enroll.html               # Step 2 — registration form + face capture
│   ├── waiting.html              # Step 3 — pre-exam checks + countdown
│   ├── exam.html                 # Step 4 — live proctored exam
│   ├── submitted.html            # Exam submission confirmation
│   ├── invigilator_login.html    # Invigilator credentials
│   └── invigilator.html          # Live dashboard
├── modules/
│   ├── face_recognition.py       # Enrollment encoding + live verification
│   ├── gaze_detection.py         # MediaPipe head pose + gaze + lip movement
│   ├── object_detection.py       # YOLOv8n phone/book/person detection
│   └── decision_engine.py        # Cheating score calculation
├── app.py                        # Flask application + all API routes
├── requirements.txt              # Python dependencies
└── README.md
```

---

## ⚙️ Installation

### Prerequisites
- Python 3.8+
- pip
- Webcam (required for proctoring)
- Virtual environment (recommended)
- **Windows only:** `cmake` and Visual Studio Build Tools (C++ compiler) required for `face_recognition`

### Step 1 — Create and activate a virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python -m venv venv
source venv/bin/activate
```

> ⚠️ **Windows PowerShell error** `running scripts is disabled`? Run this first:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install flask flask-cors flask-sqlalchemy flask-jwt-extended werkzeug opencv-python face_recognition mediapipe ultralytics openvino numpy
```

### Step 3 — Download the MediaPipe face model
```bash
# Windows PowerShell
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile "face_landmarker.task"

# Mac / Linux
wget -O face_landmarker.task "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
```

### Step 4 — Place your trained YOLO model
Copy your trained model into the project folder:
```
SecureExam/
├── best_openvino_model/    ← preferred (1.66× faster on CPU)
│   ├── best.xml
│   └── best.bin
└── best.pt                 ← fallback PyTorch model
```
> If `best_openvino_model/` is present it is used automatically. If not, the system falls back to `best.pt`.

### Step 5 — Initialise the database
```bash
flask init-db
```

### Step 6 — Seed sample data for testing
```bash
flask seed-db
```

This creates:
- Invigilator: `noura@bue.edu.eg` / `password123`
- Students: `BUE-21-001` to `BUE-21-005` / `password123`

### Step 7 — Run the application
```bash
python app.py
```

Open `http://localhost:5000` in your browser. ✅

---

## 🔑 Environment Variables

Create a `.env` file in the project root:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
DATABASE_URL=sqlite:///secureexam.db
PORT=5000
```

---

## 🗺️ User Flows

### Student Flow
```
landing.html
↓
student_login.html   (Step 1 — credentials)
↓
enroll.html          (Step 2 — registration form → 3-photo face capture)
↓
waiting.html         (Step 3 — system checks + countdown)
↓
exam.html            (Step 4 — live proctored exam, 90 min, 20 questions)
↓
submitted.html       (confirmation screen)
```

### Invigilator Flow
```
landing.html
↓
invigilator_login.html
↓
invigilator.html     (Overview / Students / Alerts / Reports / Settings)
```

---

## 🌐 Page Routes

| Route | Template | Description |
|-------|----------|-------------|
| `/` | `landing.html` | Role selection |
| `/student_login` | `student_login.html` | Student credentials |
| `/enroll` | `enroll.html` | Registration + face capture |
| `/waiting` | `waiting.html` | Pre-exam waiting room |
| `/exam` | `exam.html` | Live proctored exam |
| `/submitted` | `submitted.html` | Submission confirmation |
| `/invigilator_login` | `invigilator_login.html` | Invigilator credentials |
| `/invigilator` | `invigilator.html` | Live dashboard |

---

## 🔌 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Student login — returns JWT |
| POST | `/api/auth/logout` | Clear session |
| POST | `/api/auth/register` | Register new student |
| POST | `/api/auth/invig` | Invigilator login — returns JWT |

### Face Enrollment
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/enroll/capture` | Send one enrollment photo frame (base64) |
| POST | `/api/enroll/confirm` | Finalise enrollment from 3 captured frames |

### Identity Verification
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/verify` | Compare live frame against stored encoding |

### Exam
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/exam/status` | Get exam readiness status |
| POST | `/api/exam/start` | Create exam session |
| GET | `/api/exam/questions` | Fetch all 20 questions |
| POST | `/api/exam/answer` | Log a single answer (audit trail) |
| POST | `/api/exam/submit` | Final submission |
| GET | `/api/exam/instructions` | Get exam instructions |

### Proctoring
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/proctor/frame` | Analyse webcam frame (face + gaze + YOLO) |

### Invigilator Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/invig/students` | All active students with risk scores |
| GET | `/api/invig/alerts` | Recent alert log |
| GET | `/api/invig/student/<id>` | Single student session detail |
| POST | `/api/invig/student/<id>/flag` | Flag student session |
| POST | `/api/invig/student/<id>/block` | Block student account |

---

## 🧠 AI Modules

### Module 1 — Face Recognition (`modules/face_recognition.py`)
Uses the `face_recognition` library (built on dlib ResNet). Captures 3 photos during enrollment and stores a **128-dimensional** face embedding. Verifies identity every 4 seconds during the exam.

| Parameter | Value |
|-----------|-------|
| Embedding dimensions | 128-d |
| Acceptance threshold (Euclidean distance) | **≤ 0.55** |
| Library default (not used) | 0.60 |
| Same-person max distance (test set) | ≤ 0.27 |
| Identity check frequency | Every 30 frames (~4 sec) |

> Threshold set to 0.55 (stricter than 0.60 default) because a false accept — an impostor passing — is more damaging than a false reject in an exam context.

---

### Module 2 — Object Detection (`modules/object_detection.py`)
Fine-tuned **YOLOv8n** on a custom exam-proctoring dataset. Exported to **OpenVINO** format for 1.66× CPU speedup. Detects 5 classes: `phone`, `extra_person`, `book`, `laptop`, `student`.

| Metric | Value |
|--------|-------|
| mAP@0.5 | **0.978** |
| mAP@0.5:0.95 | 0.834 |
| Precision | 0.956 |
| Recall | 0.968 |
| Validation set size | 447 images |
| Training epochs | 80 |
| PyTorch speed | 137.7 ms/frame → 7.3 FPS |
| OpenVINO speed | 83.1 ms/frame → **12.0 FPS** |

**Per-class mAP@0.5:**

| Class | mAP@0.5 |
|-------|---------|
| student | 0.994 |
| laptop | 0.984 |
| phone | 0.983 |
| extra_person | 0.966 |
| book | 0.964 |

---

### Module 3 — Gaze Detection (`modules/gaze_detection.py`)
Uses MediaPipe FaceMesh to extract **478 facial landmarks** per frame. Computes head pose via `cv2.solvePnP`, gaze direction from iris landmarks, and talking from lip distance ratio (MAR).

| Signal | Threshold |
|--------|-----------|
| Head yaw (looking sideways) | **> 35°** |
| Head pitch (looking down) | **> 25°** |
| Gaze deviation from centre | **> 0.20** (normalised ratio) |
| Mouth Aspect Ratio — talking | **> 0.30** |

---

### Module 4 — Decision Engine (`modules/decision_engine.py`)
Fuses all module outputs into a single time-decayed cheating score:

```
score(t) = max(0, score(t-dt) - DECAY × dt) + Σ WEIGHT_i × trigger_i × dt
```

| Trigger | Weight (pts/sec) |
|---------|-----------------|
| Identity mismatch | **200** |
| Phone detected | 100 × confidence |
| Extra person | 80 × confidence |
| Book / notes | 60 × confidence |
| Looking away (head pose) | 30 |
| Gaze off-centre | 30 |
| Talking (MAR) | 20 |
| No face visible | 15 |

| Level | Score Range | Action |
|-------|------------|--------|
| NORMAL | 0 – 49 | No action |
| SUSPICIOUS | 50 – 99 | Warning shown |
| ALERT | ≥ 100 | Event logged + persisted |

> Score decays at **5 points/second** when no violations are active.  
> Alert cooldown: **3 seconds** (prevents duplicate alerts for the same event).

---

## 🛠️ Technologies

| Layer | Technology |
|-------|------------|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Backend | Python Flask |
| Database | SQLAlchemy + SQLite (dev) / PostgreSQL (prod) |
| Face Recognition | `face_recognition` library (dlib ResNet) |
| Gaze & Head Pose | MediaPipe FaceMesh + OpenCV |
| Object Detection | YOLOv8n (Ultralytics) + OpenVINO |
| Authentication | JWT (flask-jwt-extended) + Flask sessions |
| API | RESTful JSON endpoints |

---

## 🚨 Common Errors

| Error | Fix |
|-------|-----|
| `running scripts is disabled` (Windows) | Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `No module named 'face_recognition'` | Run: `pip install face-recognition` (needs cmake + VS Build Tools on Windows) |
| `face_landmarker.task not found` | Download using the command in Step 3 above |
| `best.pt not found` | Copy your trained YOLO model into the project folder |
| `cannot open webcam` | Check webcam is connected and not in use by another app |
| `Address already in use` | Another process is on port 5000 — run `python app.py --port 5001` |

---

## 🚀 Deployment

### Gunicorn (production)
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Docker
```dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

---

## 🔐 Security

- Passwords hashed with Werkzeug `generate_password_hash`
- JWT tokens with 24-hour expiration
- CORS configured with `supports_credentials=True`
- SQL injection prevention via SQLAlchemy ORM
- Blocked students cannot log in or start exams

---

## 📦 Requirements

```
flask
flask-cors
flask-sqlalchemy
flask-jwt-extended
werkzeug
opencv-python
face_recognition
mediapipe
ultralytics
openvino
numpy
```
