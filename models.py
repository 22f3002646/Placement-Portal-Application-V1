from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
import os

db = SQLAlchemy()

class UserRole(Enum):
    ADMIN = 'admin'
    COMPANY = 'company'
    STUDENT = 'student'

class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Explicit table name
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Password methods
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Company (no backref to avoid circular refs)
class Company(db.Model):
    __tablename__ = 'company'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    hr_contact = db.Column(db.String(100))
    website = db.Column(db.String(200))
    address = db.Column(db.Text)
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Student (no backref to avoid circular refs)
class Student(db.Model):
    __tablename__ = 'student'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    full_name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(15))
    branch = db.Column(db.String(50))
    year = db.Column(db.Integer)
    cgpa = db.Column(db.Float)
    resume_path = db.Column(db.String(200))
    is_blacklisted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# PlacementDrive
class PlacementDrive(db.Model):
    __tablename__ = 'placement_drive'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    eligibility = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum('pending', 'approved', 'closed'), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# Application - Links Student to Drive
class Application(db.Model):
    __tablename__ = 'application'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id', ondelete='CASCADE'), nullable=False, index=True)
    drive_id = db.Column(db.Integer, db.ForeignKey('placement_drive.id', ondelete='CASCADE'), nullable=False, index=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.Enum('applied', 'shortlisted', 'selected', 'rejected'), 
                      default='applied', index=True)
    resume_path = db.Column(db.String(200))
    
    # Prevent duplicate applications
    __table_args__ = (
        db.UniqueConstraint('student_id', 'drive_id', name='uq_student_drive'),
    )

# Helper functions for relationships (avoid circular imports)
def get_company(user):
    return Company.query.filter_by(user_id=user.id).first()

def get_student(user):
    return Student.query.filter_by(user_id=user.id).first()

def get_user_applications(user):
    if user.role != UserRole.STUDENT.value:
        return []
    student = get_student(user)
    if not student:
        return []
    return Application.query.filter_by(student_id=student.id).all()

User.company = property(get_company)
User.student = property(get_student)
User.applications = property(get_user_applications)
