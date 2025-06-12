from .app import db

class User(db.Model):
    id = db.Column(db.String(100), primary_key=True)  # Clerk user ID
    role = db.Column(db.String(20), nullable=False)  # patient, doctor, staff
    def __repr__(self):
        return f'<User {self.id}, Role {self.role}>'

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(100), db.ForeignKey('user.id'), nullable=False)
    doctor_id = db.Column(db.String(100), db.ForeignKey('user.id'), nullable=False)
    date_time = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='Pending')

    def __repr__(self):
        return f'<Appointment {self.id}>'