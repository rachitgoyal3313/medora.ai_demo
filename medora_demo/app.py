from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, TelField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from flask_wtf.csrf import CSRFProtect, CSRFError
import os
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()  # Secure random secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medora.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Helps with session persistence

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(50), nullable=False)  # Doctor, Patient, or Staff
    first_name = db.Column(db.String(50))  # For doctors and staff
    last_name = db.Column(db.String(50))  # For doctors and staff
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))  # For doctors and staff
    specialization = db.Column(db.String(100))  # For doctors
    hospital_name = db.Column(db.String(100))  # Selected hospital
    city = db.Column(db.String(100))  # For staff
    password_hash = db.Column(db.String(128), nullable=False)
    receive_updates = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), nullable=False)  # 'doctor', 'patient', or 'staff'

# Login form
class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember me')
    user_type = SelectField('User Type', choices=[
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
        ('staff', 'Staff')
    ], validators=[DataRequired()])

# Registration form
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

# Mock AI functions
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

# Handle CSRF errors
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
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
        # Get form data directly from request since HTML form names don't match WTF form names
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type')
        remember_me = request.form.get('remember_me')
        
        # Basic validation
        if not email or not password or not user_type:
            flash('Please fill in all required fields.', 'danger')
            form = LoginForm()
            return render_template('login.html', form=form)
        
        # Convert to lowercase for consistency
        user_type = user_type.lower()
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            # Check if user_type matches user's role
            if user.role != user_type:
                flash(f'Account found, but role mismatch. This account is registered as a {user.role}, not a {user_type}.', 'danger')
                form = LoginForm()
                return render_template('login.html', form=form)
            
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = bool(remember_me)  # Set session permanence based on remember me
            flash('Login successful!', 'success')
            
            # Redirect based on role
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
        flash(f'Error during login: {str(e)}', 'danger')
        form = LoginForm()
        return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        form = RegisterForm()
        return render_template('register.html', form=form)
    
    try:
        # Get form data directly from request since HTML form names don't match WTF form names
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
        
        # Basic validation
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
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email address already registered.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        # Determine role based on user_type
        role = user_type.lower()
        
        # Role-specific validation
        if role in ['doctor', 'staff'] and (not first_name or not last_name):
            flash('First name and last name are required for doctors and staff.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        if role == 'doctor' and not specialization:
            flash('Specialization is required for doctors.', 'danger')
            form = RegisterForm()
            return render_template('register.html', form=form)
        
        # Create new user
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
        
        # Log the user in automatically after registration
        session['user_id'] = user.id
        session['role'] = user.role
        flash('Registration successful! Welcome to Medora.ai!', 'success')
        
        # Redirect based on role
        if user.role == 'doctor':
            return redirect(url_for('doctor_dashboard'))
        elif user.role == 'patient':
            return redirect(url_for('patient_dashboard'))
        elif user.role == 'staff':
            return redirect(url_for('staff_dashboard'))
        
    except Exception as e:
        db.session.rollback()
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

@app.route('/staff_dashboard')
def staff_dashboard():
    if 'user_id' not in session or session.get('role') != 'staff':
        flash('Please log in as a staff member to access this dashboard.', 'danger')
        return redirect(url_for('login'))
    schedule = ai_schedule_appointment()  # Reusing for simplicity; customize as needed
    insight = ai_admin_insight()
    return render_template('staff_dashboard.html', schedule=schedule, insight=insight)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)