from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, TelField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from flask_wtf.csrf import CSRFProtect, CSRFError
import os
import random
from datetime import datetime
from flask_socketio import SocketIO, emit
import io
import json
import logging

from voice import (
    initialize_voice_service,
    start_voice_recognition,
    stop_voice_recognition,
    get_latest_transcription,
    clear_transcription_data
)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medora.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Create static/prescriptions directory if it doesn't exist
PRESCRIPTIONS_DIR = os.path.join('static', 'prescriptions')
os.makedirs(PRESCRIPTIONS_DIR, exist_ok=True)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)

initialize_voice_service(socketio)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    specialization = db.Column(db.String(100))
    hospital_name = db.Column(db.String(100))
    city = db.Column(db.String(100))
    password_hash = db.Column(db.String(128), nullable=False)
    receive_updates = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), nullable=False)

class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doctor_name = db.Column(db.String(100))
    doctor_specialization = db.Column(db.String(100))
    registration_number = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    medications = db.Column(db.Text)  # JSON string for medications
    additional_instructions = db.Column(db.Text)
    accuracy = db.Column(db.Float)
    status = db.Column(db.String(50), default='Processed')

class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember me')
    user_type = SelectField('User Type', choices=[
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
        ('staff', 'Staff')
    ], validators=[DataRequired()])

class RegisterForm(FlaskForm):
    user_type = SelectField('User Type', choices=[
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
        ('staff', 'Staff')
    ], validators=[DataRequired()])
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    phone_number = TelField('Phone Number')
    specialization = SelectField('Specialization', choices=[
        ('', 'Select specialization'),
        ('General Medicine', 'General Medicine'),
        ('Cardiology', 'Cardiology'),
        ('Neurology', 'Neurology'),
        ('Orthopedics', 'Orthopedics'),
        ('Pediatrics', 'Pediatrics'),
        ('Gynecology', 'Gynecology'),
        ('Dermatology', 'Dermatology'),
        ('Psychiatry', 'Psychiatry'),
        ('Other', 'Other')
    ])
    hospital_name = StringField('Hospital/Clinic Name')
    city = StringField('City')
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    agree_terms = BooleanField('I agree to the Terms of Service and Privacy Policy', validators=[DataRequired()])
    receive_updates = BooleanField('Send me updates about new AI features')

def ai_schedule_appointment():
    doctors = ["Dr. Smith", "Dr. Johnson"]
    return f"AI suggests booking with {random.choice(doctors)} on June 15."

def ai_health_insight():
    insights = ["Your vitals are normal", "Consider a follow-up"]
    return random.choice(insights)

def ai_diagnosis():
    diagnoses = ["Possible flu", "Check for allergies"]
    return f"AI suggests: {random.choice(diagnoses)}."

def ai_admin_insight():
    insights = ["Optimize staff scheduling", "Review inventory levels"]
    return random.choice(insights)

def ai_chat_response(query):
    responses = {
        "moral dilemma": "Exploring when lying might be justified involves weighing the consequences and intentions behind the act. Would you like to discuss a specific scenario?",
        "philosophy": "What makes life meaningful varies across perspectives—some find it in relationships, others in purpose or achievement. What's your view on this?",
        "tech ethics": "AI in decision-making raises questions about accountability and bias. Would you like to explore a particular aspect, like AI in healthcare?",
        "personal ethics": "Reflecting on moral decisions can clarify your values. Want to discuss a recent decision you made?"
    }
    return responses.get(query.lower(), "I'm here to help with your health or ethical questions. Could you clarify or ask something specific?")

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.error(f'CSRF error: {str(e)}')
    flash(f'CSRF error: {str(e)}', 'danger')
    return redirect(request.url)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/select_hospital', methods=['POST'])
def select_hospital():
    if 'user_id' not in session:
        flash('Please log in to select a hospital.', 'danger')
        return redirect(url_for('login'))
    
    hospital_name = request.form.get('hospital_name')
    if hospital_name:
        user = User.query.get(session['user_id'])
        user.hospital_name = hospital_name
        db.session.commit()
        flash('Hospital selection saved successfully.', 'success')
    else:
        flash('Please select a valid hospital.', 'danger')
    
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        form = LoginForm()
        return render_template('login.html', form=form)
    
    try:
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type')
        remember_me = request.form.get('remember_me')
        
        if not email or not password or not user_type:
            flash('Please fill in all required fields.', 'danger')
            form = LoginForm()
            return render_template('login.html', form=form)
        
        user_type = user_type.lower()
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if user.role != user_type:
                flash(f'Account found, but role mismatch. This account is registered as a {user.role}, not a {user_type}.', 'danger')
                form = LoginForm()
                return render_template('login.html', form=form)
            
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = bool(remember_me)
            flash('Login successful!', 'success')
            
            if user.role == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            elif user.role == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user.role == 'staff':
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid role in database.', 'danger')
                form = LoginForm()
                return render_template('login.html', form=form)
        else:
            flash('Invalid email or password.', 'danger')
            form = LoginForm()
            return render_template('login.html', form=form)
            
    except Exception as e:
        logger.error(f'Login error: {str(e)}')
        flash(f'Error during login: {str(e)}', 'danger')
        form = LoginForm()
        return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        form = RegisterForm()
        return render_template('register.html', form=form)
    
    try:
        user_type = request.form.get('user_type')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        specialization = request.form.get('specialization')
        hospital_name = request.form.get('hospital_name')
        city = request.form.get('city')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        terms = request.form.get('agree_terms')
        receive_updates = request.form.get('receive_updates')
        
        if not email or not password or not user_type:
            flash('Please fill in all required fields.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if not terms:
            flash('You must agree to the Terms of Service and Privacy Policy.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if User.query.filter_by(email=email).first():
            flash('Email address already registered.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        role = user_type.lower()
        
        if role in ['doctor', 'staff'] and (not first_name or not last_name):
            flash('First name and last name are required for doctors and staff.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if role == 'doctor' and not specialization:
            flash('Specialization is required for doctors.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        password_hash = generate_password_hash(password)
        user = User(
            user_type=user_type,
            first_name=first_name if role in ['doctor', 'staff'] else None,
            last_name=last_name if role in ['doctor', 'staff'] else None,
            email=email,
            phone_number=phone_number if role in ['doctor', 'staff'] else None,
            specialization=specialization if role == 'doctor' else None,
            hospital_name=hospital_name,
            city=city if role == 'staff' else None,
            password_hash=password_hash,
            receive_updates=bool(receive_updates),
            role=role
        )
        
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        session['role'] = user.role
        flash('Registration successful! Welcome to Medora.ai!', 'success')
        
        if user.role == 'doctor':
            return redirect(url_for('doctor_dashboard'))
        elif user.role == 'patient':
            return redirect(url_for('patient_dashboard'))
        elif user.role == 'staff':
            return redirect(url_for('staff_dashboard'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Registration error: {str(e)}')
        flash(f'Error during registration: {str(e)}', 'danger')
        form = RegisterForm()
        return render_template('register.html', form=form)

@app.route('/get_started')
def get_started():
    return redirect(url_for('login'))

@app.route('/start_free_trial')
def start_free_trial():
    return redirect(url_for('login'))

@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user_id' not in session or session.get('role') != 'patient':
        flash('Please log in as a patient to access this dashboard.', 'danger')
        return redirect(url_for('login'))
    appointment = ai_schedule_appointment()
    insight = ai_health_insight()
    return render_template('patient_dashboard.html', appointment=appointment, insight=insight)

@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user_id' not in session or session.get('role') != 'doctor':
        flash('Please log in as a doctor to access this dashboard.', 'danger')
        return redirect(url_for('login'))
    diagnosis = ai_diagnosis()
    return render_template('doctor_dashboard.html', diagnosis=diagnosis)

@app.route('/speak_to_prescribe')
def speak_to_prescribe():
    if 'user_id' not in session or session.get('role') != 'doctor':
        flash('Please log in as a doctor to access this feature.', 'danger')
        return redirect(url_for('login'))
    return render_template('speak_to_prescribe.html')

@app.route('/staff_dashboard')
def staff_dashboard():
    if 'user_id' not in session or session.get('role') != 'staff':
        flash('Please log in as a staff member to access this dashboard.', 'danger')
        return redirect(url_for('login'))
    schedule = ai_schedule_appointment()
    insight = ai_admin_insight()
    return render_template('staff_dashboard.html', schedule=schedule, insight=insight)

@app.route('/ocr_prescriptions', methods=['GET', 'POST'])
def ocr_prescriptions():
    if 'user_id' not in session or session.get('role') != 'patient':
        flash('Please log in as a patient to access this feature.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        try:
            file = request.files.get('prescription_file')
            if not file:
                flash('No file uploaded.', 'danger')
                return redirect(url_for('ocr_prescriptions'))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prescription_scan_{timestamp}.jpg"
            filepath = os.path.join(PRESCRIPTIONS_DIR, filename)
            file.save(filepath)
            
            medications = [
                {
                    "name": "Metformin 500mg",
                    "dosage": "1 tablet",
                    "frequency": "Twice daily",
                    "duration": "30 days",
                    "instructions": "After meals"
                },
                {
                    "name": "Atorvastatin 20mg",
                    "dosage": "1 tablet",
                    "frequency": "Once daily",
                    "duration": "30 days",
                    "instructions": "At bedtime"
                }
            ]
            prescription = Prescription(
                user_id=user.id,
                doctor_name="Dr. Rajesh Kumar",
                doctor_specialization="Cardiology",
                registration_number="MH-12345",
                date=datetime.now(),
                medications=json.dumps(medications),
                additional_instructions="Take medications as prescribed. Monitor blood sugar levels regularly. Follow up in 2 weeks for review.",
                accuracy=94.0,
                status="Processed"
            )
            db.session.add(prescription)
            db.session.commit()
            
            flash('Prescription uploaded and processed successfully.', 'success')
            return redirect(url_for('ocr_prescriptions'))
        
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error processing prescription upload: {str(e)}')
            flash(f'Error processing upload: {str(e)}', 'danger')
            return redirect(url_for('ocr_prescriptions'))
    
    recent_prescriptions = Prescription.query.filter_by(user_id=user.id).order_by(Prescription.date.desc()).limit(3).all()
    return render_template('ocr_prescriptions.html', user=user, recent_prescriptions=recent_prescriptions)

@app.route('/medora_chat', methods=['GET', 'POST'])
def medora_chat():
    if 'user_id' not in session or session.get('role') != 'patient':
        flash('Please log in as a patient to access this feature.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        try:
            query = request.form.get('query')
            if not query:
                flash('Please enter a query.', 'danger')
                return redirect(url_for('medora_chat'))
            
            response = ai_chat_response(query)
            return render_template('medora_chat.html', user=user, response=response, query=query)
        
        except Exception as e:
            logger.error(f'Error processing chat query: {str(e)}')
            flash(f'Error processing query: {str(e)}', 'danger')
            return redirect(url_for('medora_chat'))
    
    return render_template('medora_chat.html', user=user)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/process_prescription', methods=['POST'])
@csrf.exempt
def process_prescription():
    logger.debug('Processing prescription request')
    if 'user_id' not in session or session.get('role') != 'doctor':
        logger.error('Unauthorized access to process_prescription')
        return jsonify({'error': 'Unauthorized, please log in as a doctor'}), 401
    
    data = request.get_json()
    transcription = data.get('transcription', '')
    
    try:
        doctor = User.query.get(session['user_id'])
        if not doctor:
            logger.error('Doctor not found for user_id: %s', session['user_id'])
            return jsonify({'error': 'Doctor not found'}), 404
    
        prescription_html = f"""
        <div class="prescription-header">
            <div class="doctor-info">
                <div class="doctor-avatar">{doctor.first_name[0]}{doctor.last_name[0] if doctor.last_name else ''}</div>
                <div class="doctor-details">
                    <h3>Dr. {doctor.first_name} {doctor.last_name if doctor.last_name else ''}</h3>
                    <p>{doctor.specialization if doctor.specialization else 'General Medicine'}</p>
                </div>
            </div>
            <div class="prescription-date">Date: {datetime.now().strftime('%B %d, %Y')}</div>
        </div>
        <div class="patient-info">
            <div class="patient-name">Patient: [Extracted from voice]</div>
            <div class="patient-details">Voice input: {transcription[:100]}...</div>
        </div>
        <div style="padding: 20px; background: #f8f9fa; border-radius: 12px; margin-top: 20px;">
            <p>Prescription details extracted from voice input will appear here.</p>
            <p>For demo purposes, showing the transcription:</p>
            <p style="font-style: italic;">{transcription}</p>
        </div>
        <div class="prescription-actions">
            <button class="action-btn primary" onclick="savePrescription()">
                💾 Save Prescription
            </button>
            <button class="action-btn" onclick="printPrescription()">
                🖨️ Print
            </button>
            <button class="action-btn" onclick="sendPrescription()">
                📧 Send to Patient
            </button>
        </div>
        """
        
        logger.debug('Prescription processed successfully')
        return jsonify({'html': prescription_html})
    
    except Exception as e:
        logger.error(f'Error in process_prescription: {str(e)}')
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/export_prescription', methods=['POST'])
@csrf.exempt
def export_prescription():
    logger.debug('Export prescription request received')
    if 'user_id' not in session or session.get('role') != 'doctor':
        logger.error('Unauthorized access to export_prescription')
        return jsonify({'error': 'Unauthorized, please log in as a doctor'}), 401
    
    data = request.get_json()
    transcription = data.get('transcription', '')
    
    try:
        doctor = User.query.get(session['user_id'])
        if not doctor:
            logger.error('Doctor not found for user_id: %s', session['user_id'])
            return jsonify({'error': 'Doctor not found'}), 404
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        html_content = f"""
        <div class="prescription-header">
            <div class="doctor-info">
                <div class="doctor-avatar">{doctor.first_name[0]}{doctor.last_name[0] if doctor.last_name else ''}</div>
                <div class="doctor-details">
                    <h3>Dr. {doctor.first_name} {doctor.last_name if doctor.last_name else ''}</h3>
                    <p>{doctor.specialization if doctor.specialization else 'General Medicine'}</p>
                </div>
            </div>
            <div class="prescription-date">Date: {datetime.now().strftime('%B %d, %Y')}</div>
        </div>
        <div class="patient-info">
            <div class="patient-name">Patient: [Extracted from voice]</div>
            <div class="patient-details">Voice input: {transcription[:100]}...</div>
        </div>
        <div style="padding: 20px; background: #f8f9fa; border-radius: 12px; margin-top: 20px;">
            <p>Prescription details extracted from voice input will appear here.</p>
            <p>For demo purposes, showing the transcription:</p>
            <p style="font-style: italic;">{transcription}</p>
        </div>
        <div class="prescription-actions">
            <button class="action-btn primary" onclick="savePrescription()">💾 Save Prescription</button>
            <button class="action-btn" onclick="printPrescription()">🖨️ Print</button>
            <button class="action-btn" onclick="sendPrescription()">📧 Send to Patient</button>
        </div>
        """
        
        text_content = f"""Prescription
Date: {datetime.now().strftime('%B %d, %Y')}
Doctor: Dr. {doctor.first_name} {doctor.last_name if doctor.last_name else ''}
Specialization: {doctor.specialization if doctor.specialization else 'General Medicine'}
Patient: [Extracted from voice]
Prescription Details: {transcription}
"""
        text_filename = os.path.join(PRESCRIPTIONS_DIR, f"prescription_{timestamp}.txt")
        with open(text_filename, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        json_content = {
            "date": datetime.now().strftime('%B %d, %Y'),
            "doctor": f"Dr. {doctor.first_name} {doctor.last_name if doctor.last_name else ''}",
            "specialization": doctor.specialization if doctor.specialization else 'General Medicine',
            "patient": "[Extracted from voice]",
            "prescription_details": transcription
        }
        json_filename = os.path.join(PRESCRIPTIONS_DIR, f"prescription_{timestamp}.json")
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, indent=2)
        
        latex_content = r"""
        \documentclass[a4paper,12pt]{article}
        \usepackage[utf8]{inputenc}
        \usepackage{geometry}
        \geometry{margin=1in}
        \usepackage{parskip}
        \usepackage{titlesec}
        \titleformat{\section}{\large\bfseries}{\thesection}{1em}{}
        \usepackage{noto}

        \begin{document}

        \section*{Prescription}
        \textbf{Date:} """ + datetime.now().strftime('%B %d, %Y') + r""" \\
        \textbf{Doctor:} Dr. """ + f"{doctor.first_name} {doctor.last_name if doctor.last_name else ''}" + r""" \\
        \textbf{Specialization:} """ + (doctor.specialization if doctor.specialization else 'General Medicine') + r""" \\
        \textbf{Patient:} [Extracted from voice] \\
        \textbf{Prescription Details:} """ + transcription.replace('\n', '\\\\') + r"""

        \end{document}
        """
        latex_filename = os.path.join(PRESCRIPTIONS_DIR, f"prescription_{timestamp}.tex")
        with open(latex_filename, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        logger.debug('Prescription exported successfully')
        return jsonify({
            'html': html_content,
            'text_url': f"/{text_filename}",
            'pdf_url': f"/{latex_filename}",
            'json_url': f"/{json_filename}"
        })
    
    except Exception as e:
        logger.error(f'Error in export_prescription: {str(e)}')
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    try:
        return send_file(os.path.join('static', filename))
    except FileNotFoundError:
        logger.error(f'Static file not found: {filename}')
        return jsonify({'error': 'File not found'}), 404

@app.route('/start_recording', methods=['POST'])
@csrf.exempt
def start_recording_route():
    success = start_voice_recognition()
    return jsonify({'success': success}), 200 if success else 500

@app.route('/stop_recording', methods=['POST'])
@csrf.exempt
def stop_recording_route():
    transcription = stop_voice_recognition()
    return jsonify({'transcription': transcription}), 200

@app.route('/get_transcription', methods=['GET'])
@csrf.exempt
def get_transcription():
    transcription = get_latest_transcription()
    return jsonify({'transcription': transcription}), 200

@app.route('/clear_recording', methods=['POST'])
@csrf.exempt
def clear_recording():
    clear_transcription_data()
    return jsonify({'success': True}), 200

# SocketIO event handlers
@socketio.on('connect', namespace='/voice')
def handle_voice_connect():
    logger.debug('Client connected to /voice namespace')
    emit('status', {'message': 'Connected to voice service'})

@socketio.on('start_recording', namespace='/voice')
def handle_start_recording():
    logger.debug('Starting voice recognition')
    if start_voice_recognition():
        emit('status', {'message': 'Recording started'})
    else:
        emit('error', {'message': 'Failed to start recording'})

@socketio.on('stop_recording', namespace='/voice')
def handle_stop_recording():
    logger.debug('Stopping voice recognition')
    transcription = stop_voice_recognition()
    emit('status', {'message': 'Recording stopped', 'transcription': transcription})

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)