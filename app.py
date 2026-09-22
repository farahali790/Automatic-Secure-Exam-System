"""
SecureExam - AI-Powered Proctored Exam System
app.py — Main Flask Application
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os, json

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app, supports_credentials=True)

app.config['SECRET_KEY']                     = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI']        = os.environ.get('DATABASE_URL', 'sqlite:///secureexam.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY']                 = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-prod')
app.config['JWT_ACCESS_TOKEN_EXPIRES']       = timedelta(hours=24)

db  = SQLAlchemy(app)
jwt = JWTManager(app)

# ── AI modules ──────────────────────────────────────────
from modules.face_recognition import FaceRecognitionModule
from modules.gaze_detection   import GazeDetectionModule
from modules.object_detection import ObjectDetectionModule
from modules.decision_engine  import DecisionEngine

face_recognition_module = FaceRecognitionModule(tolerance=0.55)
gaze_detection_module   = GazeDetectionModule()
object_detection_module = ObjectDetectionModule()
decision_engine_module  = DecisionEngine()


# ════════════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════════════

class Student(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.String(50),  unique=True, nullable=False)
    full_name     = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    face_encoding = db.Column(db.Text)
    enrolled_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime)
    is_blocked    = db.Column(db.Boolean, default=False)

    def set_password(self, pw):   self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)


class Invigilator(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    last_login    = db.Column(db.DateTime)
    is_active     = db.Column(db.Boolean, default=True)

    def set_password(self, pw):   self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)


class ExamSession(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    exam_id    = db.Column(db.Integer, nullable=False, default=1)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time   = db.Column(db.DateTime)
    status     = db.Column(db.String(20), default='active')
    answers    = db.Column(db.JSON)
    flagged    = db.Column(db.JSON)
    time_taken = db.Column(db.Integer)


class ProctoringAlert(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey('exam_session.id'), nullable=False)
    alert_type  = db.Column(db.String(100), nullable=False)
    severity    = db.Column(db.String(20),  default='warning')
    details     = db.Column(db.JSON)
    cheat_score = db.Column(db.Integer, default=0)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed    = db.Column(db.Boolean, default=False)


# ════════════════════════════════════════════════════════
# PAGE ROUTES
# ════════════════════════════════════════════════════════

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/student')
def student_portal():
    return render_template('student.html')

@app.route('/student_login')
def student_login():
    return redirect(url_for('student_portal'))

@app.route('/enroll')
def enroll():
    return redirect(url_for('student_portal'))

@app.route('/waiting')
def waiting():
    return render_template('waiting.html')

@app.route('/exam')
def exam():
    return render_template('exam.html')

@app.route('/submitted')
def submitted():
    return render_template('submitted.html')

@app.route('/invigilator_login', methods=['GET', 'POST'])
def invig_login():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')
        invig    = Invigilator.query.filter_by(email=email).first()
        if not invig or not invig.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('invig_login'))
        invig.last_login = datetime.utcnow()
        db.session.commit()
        session['invig_id']   = invig.id
        session['invig_name'] = invig.name
        return redirect(url_for('invigilator'))
    return render_template('invigilator_login.html')

@app.route('/invigilator')
def invigilator():
    return render_template('invigilator.html')


# ════════════════════════════════════════════════════════
# API — AUTH
# ════════════════════════════════════════════════════════

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data     = request.get_json()
    sid      = data.get('student_id') or data.get('studentId')
    password = data.get('password')
    student  = Student.query.filter_by(student_id=sid).first()
    if not student or not student.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401
    if student.is_blocked:
        return jsonify({'message': 'Account blocked'}), 403
    student.last_login = datetime.utcnow()
    db.session.commit()
    token = create_access_token(identity=str(student.id))
    return jsonify({'success': True, 'token': token,
                    'student': {'name': student.full_name, 'id': student.student_id}}), 200

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/auth/invig', methods=['POST'])
def api_invig_login():
    data     = request.get_json()
    email    = data.get('email')
    password = data.get('password')
    invig    = Invigilator.query.filter_by(email=email).first()
    if not invig or not invig.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401
    token = create_access_token(identity=f'invig-{invig.id}')
    return jsonify({'success': True, 'token': token}), 200

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not all(k in data for k in ['full_name', 'student_id', 'email', 'password']):
        return jsonify({'message': 'Missing required fields'}), 400
    if Student.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Email already registered'}), 409
    if Student.query.filter_by(student_id=data['student_id']).first():
        return jsonify({'message': 'Student ID already registered'}), 409
    s = Student(student_id=data['student_id'], full_name=data['full_name'], email=data['email'])
    s.set_password(data['password'])
    db.session.add(s)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Registration successful'}), 201


# ════════════════════════════════════════════════════════
# API — ENROLLMENT
# ════════════════════════════════════════════════════════

@app.route('/api/enroll/capture', methods=['POST'])
@jwt_required()
def api_enroll_capture():
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')
    index      = data.get('index', 0)
    encoding   = face_recognition_module.extract_encoding(
        frame_b64, student_id=student_id, index=index)
    if encoding is None:
        return jsonify({'success': False, 'error': 'no_face_detected', 'photo_index': index}), 400
    return jsonify({'success': True, 'photo_index': index}), 200

@app.route('/api/enroll/confirm', methods=['POST'])
@jwt_required()
def api_enroll_confirm():
    student_id = get_jwt_identity()
    encoding   = face_recognition_module.get_average_encoding(student_id)
    if encoding is None:
        return jsonify({'success': False, 'error': 'no_captures_buffered'}), 400
    if not student_id or not str(student_id).isdigit():
        return jsonify({'success': False, 'error': 'invalid_identity'}), 400
    student = Student.query.get(int(student_id))
    student.face_encoding = json.dumps(encoding)
    student.enrolled_at   = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Enrollment complete'}), 200


# ════════════════════════════════════════════════════════
# API — EXAM
# ════════════════════════════════════════════════════════

@app.route('/api/exam/status', methods=['GET'])
def api_exam_status():
    return jsonify({'status': 'ready', 'title': 'Software Engineering — Final Exam',
                    'duration': 90, 'total_questions': 20,
                    'instructions': 'Read all questions carefully. Do not leave camera view.'}), 200

@app.route('/api/exam/questions', methods=['GET'])
def api_exam_questions():
    questions = [
        {'id':1,  'text':'Which design pattern defines a one-to-many dependency so that when one object changes state, all its dependents are notified?', 'options':['Singleton','Observer','Factory Method','Decorator'], 'difficulty':'medium','marks':5},
        {'id':2,  'text':'In Agile development, what is the typical length of a Sprint?', 'options':['1 week','2–4 weeks','3 months','6 months'], 'difficulty':'easy','marks':5},
        {'id':3,  'text':'Which UML diagram best represents the sequence of messages exchanged between objects over time?', 'options':['Class Diagram','Use Case Diagram','Sequence Diagram','Component Diagram'], 'difficulty':'easy','marks':5},
        {'id':4,  'text':'What does the "L" in the SOLID principles stand for?', 'options':['Linear Composition','Liskov Substitution','Lazy Loading','Loose Coupling'], 'difficulty':'medium','marks':5},
        {'id':5,  'text':'Which testing approach tests individual components in isolation?', 'options':['Integration Testing','System Testing','Unit Testing','Acceptance Testing'], 'difficulty':'easy','marks':5},
        {'id':6,  'text':'What is the primary goal of refactoring?', 'options':['Add new features','Fix bugs','Improve code structure without changing behaviour','Increase performance'], 'difficulty':'medium','marks':5},
        {'id':7,  'text':'In version control, what does a "merge conflict" indicate?', 'options':['A build error','Two branches modified the same code in incompatible ways','A failed test','Missing dependencies'], 'difficulty':'medium','marks':5},
        {'id':8,  'text':'Which Agile ceremony is used to reflect on the process and improve team practices?', 'options':['Sprint Planning','Daily Standup','Sprint Review','Sprint Retrospective'], 'difficulty':'easy','marks':5},
        {'id':9,  'text':'What does MVC stand for in software architecture?', 'options':['Module View Controller','Model View Controller','Multi-View Component','Managed Visual Code'], 'difficulty':'easy','marks':5},
        {'id':10, 'text':'Which principle states that a class should have only one reason to change?', 'options':['Open-Closed Principle','Single Responsibility Principle','Dependency Inversion','Interface Segregation'], 'difficulty':'medium','marks':5},
        {'id':11, 'text':'What is a use case diagram primarily used for?', 'options':['Database design','System architecture','Capturing system requirements from user perspective','Network topology'], 'difficulty':'easy','marks':5},
        {'id':12, 'text':'Which model is known as the "waterfall" model?', 'options':['Agile','Sequential/Linear SDLC','Spiral','RAD'], 'difficulty':'easy','marks':5},
        {'id':13, 'text':'What is the purpose of a stub in software testing?', 'options':['Replace a real component temporarily','Test UI elements','Generate random data','Monitor network calls'], 'difficulty':'hard','marks':5},
        {'id':14, 'text':'Which Git command creates a new branch and switches to it?', 'options':['git merge','git checkout -b','git pull','git stash'], 'difficulty':'easy','marks':5},
        {'id':15, 'text':'What does "coupling" mean in software engineering?', 'options':['How a module is divided','Degree of interdependence between modules','Number of classes in a module','Code reuse level'], 'difficulty':'medium','marks':5},
        {'id':16, 'text':'Which diagram shows the static structure of a system through classes and relationships?', 'options':['Activity Diagram','Sequence Diagram','Class Diagram','State Diagram'], 'difficulty':'easy','marks':5},
        {'id':17, 'text':'What does "cohesion" refer to in software design?', 'options':['Number of dependencies','How closely related the responsibilities of a module are','Code length','Team organization'], 'difficulty':'medium','marks':5},
        {'id':18, 'text':'Which testing technique does NOT require knowledge of the internal code structure?', 'options':['White-box testing','Unit testing','Black-box testing','Code review'], 'difficulty':'medium','marks':5},
        {'id':19, 'text':'In software metrics, what does LOC stand for?', 'options':['Level of Complexity','Lines of Code','List of Classes','Logic Operation Count'], 'difficulty':'easy','marks':5},
        {'id':20, 'text':'Which Agile framework uses roles: Scrum Master, Product Owner, and Development Team?', 'options':['Kanban','XP (Extreme Programming)','Scrum','SAFe'], 'difficulty':'easy','marks':5},
    ]
    return jsonify({'questions': questions, 'duration': 90}), 200

@app.route('/api/exam/answer', methods=['POST'])
@jwt_required()
def api_save_answer():
    return jsonify({'success': True}), 200

@app.route('/api/exam/submit', methods=['POST'])
@jwt_required()
def api_submit_exam():
    student_id = get_jwt_identity()
    if not student_id or not str(student_id).isdigit():
        return jsonify({'success': False, 'message': 'Invalid identity'}), 400
    data   = request.get_json()
    active = ExamSession.query.filter_by(student_id=student_id, status='active').first()
    if not active:
        active = ExamSession(student_id=student_id, exam_id=1)
        db.session.add(active)
    active.answers    = data.get('answers')
    active.flagged    = data.get('flagged', [])
    active.time_taken = data.get('time_taken')
    active.end_time   = datetime.utcnow()
    active.status     = 'completed'
    # Clear decision engine state for this student when exam ends
    decision_engine_module.reset(str(student_id))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Exam submitted successfully'}), 200

@app.route('/api/exam/start', methods=['POST'])
@jwt_required()
def api_start_exam():
    student_id = get_jwt_identity()
    if not student_id or not str(student_id).isdigit():
        return jsonify({'success': False, 'message': 'Invalid identity'}), 400
    data    = request.get_json()
    exam_id = data.get('exam_id', 1) if data else 1
    existing = ExamSession.query.filter_by(
        student_id=student_id, exam_id=exam_id, status='active').first()
    if existing:
        return jsonify({'success': True, 'session_id': existing.id}), 200
    s = ExamSession(student_id=student_id, exam_id=exam_id)
    db.session.add(s)
    db.session.commit()
    return jsonify({'success': True, 'session_id': s.id}), 201

@app.route('/api/exam/instructions', methods=['GET'])
def api_exam_instructions():
    return jsonify({'instructions': '<ul><li>Do not use phones or notes</li><li>Keep face in camera frame</li><li>Do not switch tabs</li></ul>'}), 200


# ════════════════════════════════════════════════════════
# API — PROCTORING
# ════════════════════════════════════════════════════════

@app.route('/api/verify', methods=['POST'])
@jwt_required()
def api_verify():
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')
    if not student_id or not str(student_id).isdigit():
        return jsonify({'matched': False, 'error': 'not_enrolled'}), 400
    student = Student.query.get(int(student_id))
    if not student or not student.face_encoding:
        return jsonify({'matched': False, 'error': 'not_enrolled'}), 400
    stored = json.loads(student.face_encoding)
    result = face_recognition_module.verify(frame_b64, stored)
    return jsonify({
        'matched':    result['matched'],
        'confidence': round((1.0 - (result['distance'] or 1.0)) * 100, 1),
    }), 200


@app.route('/api/proctor/frame', methods=['POST'])
@jwt_required()
def api_proctor_frame():
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')

    # Guard: reject invigilator tokens
    if not student_id or not str(student_id).isdigit():
        return jsonify({'cheat_score': 0, 'flags': []}), 200

    face_result = None
    gaze_result = None
    obj_result  = None

    # 1. Face verification
    student = Student.query.get(int(student_id))
    if student and student.face_encoding:
        stored      = json.loads(student.face_encoding)
        face_result = face_recognition_module.verify(frame_b64, stored)

    # 2. Behaviour analysis
    try:
        gaze_result = gaze_detection_module.analyze(frame_b64)
    except Exception as e:
        print(f'[Gaze] error: {e}')

    # 3. Object detection — pass confidence floats so decision engine
    #    can weight them (confidence-weighted per Section 3.4 of report)
    try:
        raw_det = object_detection_module._run_yolo(frame_b64)

        def _best_conf(label):
            """Return highest confidence float for a class, or False."""
            hits = [d['confidence'] for d in raw_det if d['type'] == label]
            return max(hits) if hits else False

        obj_result = {
            'mobile_phone':    _best_conf('phone'),
            'multiple_people': _best_conf('extra_person'),
            'book':            _best_conf('book'),
        }
    except Exception as e:
        print(f'[ObjDet] error: {e}')

    # 4. Feed all results into the decision engine (time-decay formula)
    decision = decision_engine_module.update(
        student_id  = str(student_id),
        face_result = face_result,
        gaze_result = gaze_result,
        obj_result  = obj_result,
    )

    score = decision['score']
    flags = decision['triggers']
    state = decision['state']

    # 5. Persist alert when there are active flags
    #    Decision engine handles the 3-second ALERT cooldown internally
    if flags:
        try:
            active = ExamSession.query.filter_by(
                student_id=student_id, status='active').first()
            if active:
                severity = 'critical' if state == 'ALERT' else \
                           'warning'  if state == 'SUSPICIOUS' else 'info'
                alert = ProctoringAlert(
                    session_id  = active.id,
                    alert_type  = ', '.join(flags),
                    severity    = severity,
                    cheat_score = int(score),
                    details     = {'flags': flags, 'score': score, 'state': state},
                )
                db.session.add(alert)
                db.session.commit()
        except Exception as e:
            print(f'[Alert] error: {e}')

    return jsonify({'cheat_score': score, 'flags': flags}), 200


# ════════════════════════════════════════════════════════
# API — INVIGILATOR
# ════════════════════════════════════════════════════════

ALERT_META = {
    'face_mismatch':  {'icon': '👤', 'label': 'Face Mismatch'},
    'phone_detected': {'icon': '📱', 'label': 'Phone Detected'},
    'extra_person':   {'icon': '👥', 'label': 'Extra Person'},
    'book_detected':  {'icon': '📚', 'label': 'Book Detected'},
    'gaze_off':       {'icon': '👁',  'label': 'Gaze Off-Screen'},
    'head_turned':    {'icon': '↔',  'label': 'Head Turned'},
    'mouth_moving':   {'icon': '💬', 'label': 'Mouth Movement'},
    'no_face':        {'icon': '🚫', 'label': 'No Face Detected'},
}

@app.route('/api/invig/students', methods=['GET'])
@jwt_required()
def api_invig_students():
    try:
        sessions = ExamSession.query.filter_by(status='active').all()
        result   = []
        for s in sessions:
            student = Student.query.get(s.student_id)
            if not student:
                continue
            alerts  = ProctoringAlert.query.filter_by(session_id=s.id).all()
            # Use live score from decision engine if student is active,
            # otherwise fall back to the highest persisted score
            live_score = decision_engine_module.get_score(str(s.student_id))
            db_score   = max((a.cheat_score for a in alerts), default=0)
            score      = max(live_score, db_score)
            state      = decision_engine_module.get_state(str(s.student_id))
            tags = []
            for a in alerts:
                if not a.reviewed:
                    for flag in a.alert_type.split(', '):
                        meta = ALERT_META.get(flag.strip())
                        if meta and meta['label'] not in tags:
                            tags.append(meta['label'])
            elapsed = int((datetime.utcnow() - s.start_time).seconds / 60)
            result.append({
                'id':           student.student_id,
                'name':         student.full_name,
                'risk':         score,
                'status':       'flagged' if state == 'ALERT' else
                                'warned'  if state == 'SUSPICIOUS' else 'active',
                'tags':         tags,
                'progress':     '—',
                'time_elapsed': f'{elapsed}m',
            })
        return jsonify({'students': result}), 200
    except Exception as e:
        print(f'[invig/students] error: {e}')
        return jsonify({'students': [], 'error': str(e)}), 200

@app.route('/api/invig/alerts', methods=['GET'])
@jwt_required()
def api_invig_alerts():
    try:
        alerts = ProctoringAlert.query.order_by(
            ProctoringAlert.timestamp.desc()).limit(100).all()
        result = []
        for a in alerts:
            s       = ExamSession.query.get(a.session_id)
            student = Student.query.get(s.student_id) if s else None
            flags   = [f.strip() for f in a.alert_type.split(', ')]
            icons   = ' '.join(ALERT_META.get(f, {}).get('icon', '⚠') for f in flags)
            labels  = ', '.join(ALERT_META.get(f, {}).get('label', f) for f in flags)
            result.append({
                'id':           a.id,
                'level':        a.severity,
                'icon':         icons,
                'title':        labels,
                'student_name': student.full_name if student else 'Unknown',
                'student_id':   student.student_id if student else '—',
                'score':        a.cheat_score,
                'time':         a.timestamp.strftime('%H:%M:%S'),
                'date':         a.timestamp.strftime('%d %b %Y'),
                'reviewed':     a.reviewed,
            })
        return jsonify({'alerts': result}), 200
    except Exception as e:
        print(f'[invig/alerts] error: {e}')
        return jsonify({'alerts': [], 'error': str(e)}), 200

@app.route('/api/invig/student/<string:student_id>', methods=['GET'])
@jwt_required()
def api_invig_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({'message': 'Student not found'}), 404
    return jsonify({'id': student.student_id, 'name': student.full_name,
                    'blocked': student.is_blocked}), 200

@app.route('/api/invig/student/<string:student_id>/flag', methods=['POST'])
@jwt_required()
def api_flag_student(student_id):
    try:
        student = Student.query.filter_by(student_id=student_id).first()
        if student:
            s = ExamSession.query.filter_by(
                student_id=student.id, status='active').first()
            if s:
                s.status = 'flagged'
                db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/invig/student/<string:student_id>/block', methods=['POST'])
@jwt_required()
def api_block_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({'message': 'Student not found'}), 404
    student.is_blocked = True
    db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/api/invig/alerts/<int:alert_id>/review', methods=['POST'])
@jwt_required()
def api_review_alert(alert_id):
    alert = ProctoringAlert.query.get(alert_id)
    if alert:
        alert.reviewed = True
        db.session.commit()
    return jsonify({'success': True}), 200


# ════════════════════════════════════════════════════════
# ERROR HANDLERS
# ════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({'message': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    return jsonify({'message': 'Internal server error'}), 500

@jwt.unauthorized_loader
def unauthorized(e):
    return jsonify({'message': 'Unauthorized'}), 401


# ════════════════════════════════════════════════════════
# CLI COMMANDS
# ════════════════════════════════════════════════════════

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('✓ Database tables created')

@app.cli.command('seed-db')
def seed_db():
    db.drop_all()
    db.create_all()
    inv = Invigilator(name='Dr. Noura Elmaghawry', email='noura@bue.edu.eg')
    inv.set_password('password123')
    db.session.add(inv)
    for sid, name, email in [
        ('BUE-21-001', 'Ahmed Hassan',   'ahmed@bue.edu.eg'),
        ('BUE-21-002', 'Sara Mostafa',   'sara@bue.edu.eg'),
        ('BUE-21-003', 'Omar Khalil',    'omar@bue.edu.eg'),
        ('BUE-21-004', 'Nour Abdelaziz', 'nour@bue.edu.eg'),
        ('BUE-21-005', 'Youssef Salem',  'youssef@bue.edu.eg'),
    ]:
        s = Student(student_id=sid, full_name=name, email=email)
        s.set_password('password123')
        db.session.add(s)
    db.session.commit()
    print('✓ Done — noura@bue.edu.eg / password123 | BUE-21-001 to 005 / password123')


# ════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))