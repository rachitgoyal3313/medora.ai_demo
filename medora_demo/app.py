from flask import Flask, render_template, redirect, url_for, session, request
import random

app = Flask(__name__)
app.secret_key = "your_flask_secret_key"  # Replace with secure key

# Mock user data (replace with Clerk authentication)
users = {
    "patient@example.com": {"role": "patient"},
    "doctor@example.com": {"role": "doctor"}
}

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

# Landing page
@app.route('/')
def index():
    return render_template('index.html')

# Login page (simplified, replace with Clerk's hosted login)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        if email in users:
            session['user'] = email
            role = users[email]['role']
            if role == "patient":
                return redirect(url_for('patient_dashboard'))
            elif role == "doctor":
                return redirect(url_for('doctor_dashboard'))
        return "Invalid login", 403
    return render_template('login.html')

# Patient dashboard
@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user' not in session or users[session['user']]['role'] != 'patient':
        return redirect(url_for('login'))
    appointment = ai_schedule_appointment()
    insight = ai_health_insight()
    return render_template('patient_dashboard.html', appointment=appointment, insight=insight)

# Doctor dashboard(/doctor_dashboard')
@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user' not in session or users[session['user']]['role'] != 'doctor':
        return redirect(url_for('login'))
    diagnosis = ai_diagnosis()
    return render_template('doctor_dashboard.html', diagnosis=diagnosis)

if __name__ == '__main__':
    app.run(debug=True)