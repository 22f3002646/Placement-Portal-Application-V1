from flask import Flask, render_template, request, flash, redirect, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Company, Student, PlacementDrive, Application, UserRole
from config import Config
import os
import sqlite3

app = Flask(__name__)
app.config.from_object(Config)

INSTANCE_DIR = os.path.join(app.instance_path)
UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'resumes') if app.static_folder else 'static/uploads/resumes'

os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, "placement_portal.db")
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

try:
    test_conn = sqlite3.connect(DB_PATH)
    test_conn.execute("SELECT 1")
    test_conn.close()
    print("SQLite connection OK")
except Exception as e:
    print(f"SQLite test failed: {e}")


db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_tables_and_admin():
    """Create tables and default admin - SAFE idempotent version"""
    with app.app_context():
        db.create_all()
        
        # Create default admin ONLY if missing
        admin_count = User.query.filter_by(username='admin', role=UserRole.ADMIN).count()
        if admin_count == 0:
            admin = User(username='admin', email='admin@institute.com', role=UserRole.ADMIN)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Created default admin: username=admin, password=admin123")
        else:
            print("ℹ️ Admin already exists")

create_tables_and_admin()


@app.route('/')
def index():
    print("index page")
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
