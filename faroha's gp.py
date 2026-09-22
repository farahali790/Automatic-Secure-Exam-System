"""
SecureExam - AI-Powered Proctored Exam System
app.py — Main Flask Application
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, verify_jwt_in_request
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json

# ── App setup ────────────────────────────────────────────
app = Flask(__name__)
CORS(app, supports_credentials=True)  # supports_credentials needed for fetch with credentials:'include'

app.config['SECRET_KEY']                = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI']   = os.environ.get('DATABASE_URL', 'sqlite:///secureexam.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY']            = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-prod')
app.config['JWT_ACCESS_TOKEN_EXPIRES']  = timedelta(hours=24)

db  = SQLAlchemy(app)
jwt = JWTManager(app)

# ── AI modules — imported lazily so Flask starts even before
#    the Python packages are installed. Each module is None
#    until you uncomment the real import below. ────────────
face_recognition_module = None
gaze_detection_module   = None
object_detection_module = None
decision_engine_module  = None

# Uncomment these ONE BY ONE as you implement each module:
# from modules.face_recognition import FaceRecognitionModule
# face_recognition_module = FaceRecognitionModule()

# from modules.gaze_detection import GazeDetectionModule
# gaze_detection_module = GazeDetectionModule()

# from modules.object_detection import ObjectDetectionModule
# object_detection_module = ObjectDetectionModule()

# from modules.decision_engine import DecisionEngine
# decision_engine_module = DecisionEngine()


# ════════════════════════════════════════════════════════
# DATABASE MODELS
# ════════════════════════════════════════════════════════

class Student(db.Model):
    id                        = db.Column(db.Integer, primary_key=True)
    student_id                = db.Column(db.String(50),  unique=True, nullable=False)
    full_name                 = db.Column(db.String(120), nullable=False)
    email                     = db.Column(db.String(120), unique=True, nullable=False)
    password_hash             = db.Column(db.String(255), nullable=False)
    face_encoding             = db.Column(db.Text)        # JSON string of 128-d vector
    enrolled_at               = db.Column(db.DateTime, default=datetime.utcnow)
    last_login                = db.Column(db.DateTime)
    is_blocked                = db.Column(db.Boolean, default=False)

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
    id             = db.Column(db.Integer, primary_key=True)
    student_id     = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    exam_id        = db.Column(db.Integer, nullable=False, default=1)
    start_time     = db.Column(db.DateTime, default=datetime.utcnow)
    end_time       = db.Column(db.DateTime)
    status         = db.Column(db.String(20), default='active')  # active | completed | flagged
    answers        = db.Column(db.JSON)
    flagged        = db.Column(db.JSON)
    time_taken     = db.Column(db.Integer)


class ProctoringAlert(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('exam_session.id'), nullable=False)
    alert_type = db.Column(db.String(50),  nullable=False)
    severity   = db.Column(db.String(20),  default='warning')  # info | warning | critical
    details    = db.Column(db.JSON)
    cheat_score= db.Column(db.Integer, default=0)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed   = db.Column(db.Boolean, default=False)


# ════════════════════════════════════════════════════════
# PAGE ROUTES  (render HTML — NO jwt_required here)
# ════════════════════════════════════════════════════════

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        sid      = request.form.get('student_id')
        password = request.form.get('password')
        student  = Student.query.filter_by(student_id=sid).first()
        if not student or not student.check_password(password):
            flash('Invalid student ID or password.', 'error')
            return redirect(url_for('student_login'))
        if student.is_blocked:
            flash('Your account has been blocked. Contact your invigilator.', 'error')
            return redirect(url_for('student_login'))
        student.last_login = datetime.utcnow()
        db.session.commit()
        session['student_id'] = student.id
        session['student_name'] = student.full_name
        return redirect(url_for('enroll'))
    return render_template('student_login.html')

@app.route('/enroll', methods=['GET'])
def enroll():
    return render_template('enroll.html')

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
    """Student login — returns JWT for SPA/JS use"""
    data     = request.get_json()
    sid      = data.get('studentId')
    password = data.get('password')
    student  = Student.query.filter_by(student_id=sid).first()
    if not student or not student.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401
    if student.is_blocked:
        return jsonify({'message': 'Account blocked'}), 403
    student.last_login = datetime.utcnow()
    db.session.commit()
    token = create_access_token(identity=student.id)
    return jsonify({'success': True, 'token': token, 'student': {'name': student.full_name, 'id': student.student_id}}), 200

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/auth/invig', methods=['POST'])
def api_invig_login():
    """Invigilator login — returns JWT"""
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
    """Student self-registration"""
    data = request.get_json()
    required = ['full_name', 'student_id', 'email', 'password']
    if not all(k in data for k in required):
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
    """Receive one enrollment photo frame (base64 JPEG)"""
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')
    index      = data.get('index', 0)   # 0, 1, or 2

    # ── When face_recognition_module is ready: ──
    # encoding = face_recognition_module.extract_encoding(frame_b64)
    # Store encoding per index in a temp structure, then average on confirm

    return jsonify({'success': True, 'photo_index': index}), 200

@app.route('/api/enroll/confirm', methods=['POST'])
@jwt_required()
def api_enroll_confirm():
    """Finalise enrollment — average the 3 captured encodings"""
    student_id = get_jwt_identity()

    # ── When face_recognition_module is ready: ──
    # encoding = face_recognition_module.get_average_encoding(student_id)
    # student  = Student.query.get(student_id)
    # student.face_encoding = json.dumps(encoding.tolist())
    # db.session.commit()

    return jsonify({'success': True, 'message': 'Enrollment complete'}), 200


# ════════════════════════════════════════════════════════
# API — EXAM
# ════════════════════════════════════════════════════════

@app.route('/api/exam/status', methods=['GET'])
def api_exam_status():
    return jsonify({
        'status':          'ready',
        'title':           'Software Engineering — Final Exam',
        'duration':        90,
        'total_questions': 20,
        'instructions':    'Read all questions carefully. Do not leave camera view.'
    }), 200

@app.route('/api/exam/questions', methods=['GET'])
def api_exam_questions():
    """Return exam questions. Replace hardcoded list with DB query when ready."""
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
    """Log a single answer for audit trail"""
    data = request.get_json()
    # Store in session or DB — useful for crash recovery
    # question_idx = data.get('question')
    # answer_idx   = data.get('answer')
    return jsonify({'success': True}), 200

@app.route('/api/exam/submit', methods=['POST'])
@jwt_required()
def api_submit_exam():
    student_id = get_jwt_identity()
    data       = request.get_json()

    active = ExamSession.query.filter_by(student_id=student_id, status='active').first()
    if active:
        active.answers    = data.get('answers')
        active.flagged    = data.get('flagged', [])
        active.time_taken = data.get('time_taken')
        active.end_time   = datetime.utcnow()
        active.status     = 'completed'
        db.session.commit()

    return jsonify({'success': True, 'message': 'Exam submitted successfully'}), 200

@app.route('/api/exam/start', methods=['POST'])
@jwt_required()
def api_start_exam():
    student_id = get_jwt_identity()
    data       = request.get_json()
    exam_id    = data.get('exam_id', 1)
    existing   = ExamSession.query.filter_by(student_id=student_id, exam_id=exam_id, status='active').first()
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
# API — PROCTORING  (real-time frame analysis)
# ════════════════════════════════════════════════════════

@app.route('/api/verify', methods=['POST'])
@jwt_required()
def api_verify():
    """Compare live frame against stored face encoding"""
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')

    # ── When face_recognition_module is ready: ──
    # student  = Student.query.get(student_id)
    # encoding = json.loads(student.face_encoding)
    # result   = face_recognition_module.verify(frame_b64, encoding)
    # return jsonify({'matched': result['matched'], 'confidence': result['confidence']}), 200

    return jsonify({'matched': True, 'confidence': 97.3}), 200

@app.route('/api/proctor/frame', methods=['POST'])
@jwt_required()
def api_proctor_frame():
    """
    Analyse one webcam frame through all three modules.
    Called every 4 seconds by exam.js during the exam.
    Returns: { cheat_score: int, flags: list[str] }
    """
    student_id = get_jwt_identity()
    data       = request.get_json()
    frame_b64  = data.get('frame')
    flags      = []
    score      = 0

    # ── Uncomment each block as you implement the module ──

    # Face verification
    # if face_recognition_module:
    #     student  = Student.query.get(student_id)
    #     encoding = json.loads(student.face_encoding or '[]')
    #     result   = face_recognition_module.verify(frame_b64, encoding)
    #     if not result['matched']:
    #         flags.append('face_mismatch')
    #         score += 30

    # Gaze + head pose
    # if gaze_detection_module:
    #     gaze = gaze_detection_module.analyze(frame_b64)
    #     if gaze['gaze_off_screen']:
    #         flags.append('gaze_off')
    #         score += 15
    #     if gaze['head_turned']:
    #         flags.append('head_turned')
    #         score += 10
    #     if gaze['mouth_moving']:
    #         flags.append('mouth_moving')
    #         score += 10

    # Object detection
    # if object_detection_module:
    #     objects = object_detection_module.detect(frame_b64)
    #     if 'phone' in objects:
    #         flags.append('phone_detected')
    #         score += 25
    #     if 'person' in objects:
    #         flags.append('extra_person')
    #         score += 40
    #     if 'book' in objects:
    #         flags.append('book_detected')
    #         score += 15

    # Log alert if suspicious
    # if score > 0:
    #     active = ExamSession.query.filter_by(student_id=student_id, status='active').first()
    #     if active:
    #         alert = ProctoringAlert(session_id=active.id, alert_type=','.join(flags),
    #                                 severity='critical' if score>=60 else 'warning',
    #                                 cheat_score=score, details={'flags': flags})
    #         db.session.add(alert)
    #         db.session.commit()

    return jsonify({'cheat_score': score, 'flags': flags}), 200


# ════════════════════════════════════════════════════════
# API — INVIGILATOR DASHBOARD
# ════════════════════════════════════════════════════════

@app.route('/api/invig/students', methods=['GET'])
@jwt_required()
def api_invig_students():
    """All active students with risk scores"""
    sessions = ExamSession.query.filter_by(status='active').all()
    result   = []
    for s in sessions:
        student = Student.query.get(s.student_id)
        alerts  = ProctoringAlert.query.filter_by(session_id=s.id).all()
        score   = max((a.cheat_score for a in alerts), default=0)
        tags    = list({a.alert_type for a in alerts if not a.reviewed})
        result.append({
            'id':           student.student_id,
            'name':         student.full_name,
            'risk':         score,
            'status':       'flagged' if score >= 60 else 'warned' if score >= 25 else 'active',
            'tags':         tags,
            'progress':     '—',
            'time_elapsed': str(int((datetime.utcnow() - s.start_time).seconds / 60)) + 'm',
        })
    return jsonify({'students': result}), 200

@app.route('/api/invig/alerts', methods=['GET'])
@jwt_required()
def api_invig_alerts():
    """Recent alert log across all sessions"""
    alerts = ProctoringAlert.query.order_by(ProctoringAlert.timestamp.desc()).limit(50).all()
    result = []
    for a in alerts:
        s = ExamSession.query.get(a.session_id)
        student = Student.query.get(s.student_id) if s else None
        result.append({
            'level':  'crit' if a.severity == 'critical' else 'warn' if a.severity == 'warning' else 'info',
            'title':  f'{a.alert_type} — {student.full_name if student else "Unknown"}',
            'sub':    str(a.details),
            'time':   a.timestamp.strftime('%H:%M:%S'),
        })
    return jsonify({'alerts': result}), 200

@app.route('/api/invig/student/<string:student_id>', methods=['GET'])
@jwt_required()
def api_invig_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({'message': 'Student not found'}), 404
    return jsonify({'id': student.student_id, 'name': student.full_name, 'blocked': student.is_blocked}), 200

@app.route('/api/invig/student/<string:student_id>/flag', methods=['POST'])
@jwt_required()
def api_flag_student(student_id):
    session_rec = ExamSession.query.join(Student).filter(
        Student.student_id == student_id, ExamSession.status == 'active'
    ).first()
    if session_rec:
        session_rec.status = 'flagged'
        db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/api/invig/student/<string:student_id>/block', methods=['POST'])
@jwt_required()
def api_block_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({'message': 'Student not found'}), 404
    student.is_blocked = True
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
    """flask init-db — create all tables"""
    db.create_all()
    print('✓ Database tables created')

@app.cli.command('seed-db')
def seed_db():
    """flask seed-db — add sample invigilator + students for testing"""
    db.drop_all()
    db.create_all()

    inv = Invigilator(name='Dr. Noura Elmaghawry', email='noura@bue.edu.eg')
    inv.set_password('password123')
    db.session.add(inv)

    sample_students = [
        ('BUE-21-001', 'Ahmed Hassan',   'ahmed@bue.edu.eg'),
        ('BUE-21-002', 'Sara Mostafa',   'sara@bue.edu.eg'),
        ('BUE-21-003', 'Omar Khalil',    'omar@bue.edu.eg'),
        ('BUE-21-004', 'Nour Abdelaziz', 'nour@bue.edu.eg'),
        ('BUE-21-005', 'Youssef Salem',  'youssef@bue.edu.eg'),
    ]
    for sid, name, email in sample_students:
        s = Student(student_id=sid, full_name=name, email=email)
        s.set_password('password123')
        db.session.add(s)

    db.session.commit()
    print('✓ Sample data created')
    print('  Invigilator: noura@bue.edu.eg / password123')
    print('  Students: BUE-21-001 to BUE-21-005 / password123')


# ════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(
        debug=True,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )