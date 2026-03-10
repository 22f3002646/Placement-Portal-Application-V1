import os
import sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename 

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from config import Config
from models import db, User, UserRole, Student, Company, PlacementDrive, Application

# ----------------------------------------------------------------------
# App + paths
# ----------------------------------------------------------------------

app = Flask(__name__)
app.config.from_object(Config)

# Directories (created before DB init)
INSTANCE_DIR = app.instance_path
UPLOAD_DIR = os.path.join(app.static_folder, "uploads", "resumes")

os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

db_path = os.path.join(INSTANCE_DIR, "placement_portal.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

try:
    conn = sqlite3.connect(db_path)
    conn.execute("SELECT 1")
    conn.close()
except Exception as e:
    print("SQLite check failed:", e)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.template_filter('is_deadline_passed')
def is_deadline_passed(deadline):
    if not deadline:
        return True
    return deadline < datetime.now()

@app.template_filter('format_date')
def format_date(dt, format_str='%d %b %Y'):
    if dt:
        return dt.strftime(format_str)
    return 'N/A'


# ----------------------------------------------------------------------
# DB creation + default admin
# ----------------------------------------------------------------------

def init_db_and_admin():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username="admin", role=UserRole.ADMIN).first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@institute.com",
                role=UserRole.ADMIN,
                is_active=True,
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: admin/admin123")


init_db_and_admin()

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def role_required(role: UserRole):
    if (not current_user.is_authenticated) or (current_user.role != role):
        abort(403)


# ----------------------------------------------------------------------
# Auth routes
# ----------------------------------------------------------------------

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == UserRole.ADMIN:
        return redirect(url_for("admin_dashboard"))
    if current_user.role == UserRole.COMPANY:
        return redirect(url_for("company_dashboard"))
    if current_user.role == UserRole.STUDENT:
        return redirect(url_for("student_dashboard"))
    logout_user()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------

@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("student", "company"):
        abort(404)

    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already exists.", "danger")
            return render_template("register.html", role=role)

        user_role = UserRole.STUDENT if role == "student" else UserRole.COMPANY
        new_user = User(
            username=username, 
            email=email, 
            role=user_role, 
            is_active=True
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush() 
        try:
            if role == "student":
                resume_filename = None
                if 'resume' in request.files:
                    resume_file = request.files['resume']
                    if resume_file and resume_file.filename:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        original_name = secure_filename(resume_file.filename)
                        resume_filename = f"{new_user.username}_{timestamp}_{original_name}"
                        
                        upload_folder = os.path.join("static", "uploads", "resumes")
                        os.makedirs(upload_folder, exist_ok=True)
                        resume_path = os.path.join(upload_folder, resume_filename)
                        
                        resume_file.save(resume_path)
                        print(f"Resume saved: {resume_path}")  

                student = Student(
                    user_id=new_user.id,
                    full_name=request.form["full_name"],
                    contact=request.form.get("contact"),
                    branch=request.form.get("branch"),
                    year=int(request.form.get("year") or 0),
                    cgpa=float(request.form.get("cgpa") or 0),
                    skills=request.form.get("skills"),
                    education=request.form.get("education"),
                    resume_path=resume_filename,  
                )
                db.session.add(student)
                flash("Student registration successful with resume! Please log in.", "success")

            else: 
                company = Company(
                    user_id=new_user.id,
                    name=request.form["company_name"],
                    industry=request.form.get("industry"),
                    hr_contact=request.form.get("hr_contact"),
                    website=request.form.get("website"),
                    address=request.form.get("address"),
                    is_approved=False,
                    is_blacklisted=False,
                )
                db.session.add(company)
                flash("Company registered! Awaiting admin approval.", "success")

            db.session.commit()
            return redirect(url_for("login"))

        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {str(e)}", "danger")
            print(f"Registration ERROR: {e}")  
            return render_template("register.html", role=role)

    return render_template("register.html", role=role)


# ----------------------------------------------------------------------
# Admin views
# ----------------------------------------------------------------------

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    role_required(UserRole.ADMIN)

    stats = {
        "students": Student.query.count(),
        "companies": Company.query.count(),
        "applications": Application.query.count(),
        "drives": PlacementDrive.query.count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


@app.route("/admin/companies")
@login_required
def admin_companies():
    role_required(UserRole.ADMIN)
    
    query = request.args.get('q', '').strip().lower()
    companies = Company.query
    
    if query:
        companies = companies.filter(
            db.or_(
                Company.name.ilike(f'%{query}%'),
                Company.industry.ilike(f'%{query}%'),
                Company.hr_contact.ilike(f'%{query}%')
            )
        )
    
    companies = companies.order_by(Company.created_at.desc()).all()
    return render_template("admin/companies.html", companies=companies, search_query=query)


@app.route("/admin/students/<int:student_id>/blacklist")
@login_required
def admin_blacklist_student(student_id):
    role_required(UserRole.ADMIN)
    student = Student.query.get_or_404(student_id)
    student.is_blacklisted = True
    student.user.is_active = False 
    db.session.commit()
    flash(f"Student '{student.full_name}' blacklisted.", "success")
    return redirect(url_for("admin_students"))

 
@app.route("/admin/students/<int:student_id>/activate")
@login_required
def admin_activate_student(student_id):
    role_required(UserRole.ADMIN)
    student = Student.query.get_or_404(student_id)
    student.is_blacklisted = False
    student.user.is_active = True
    db.session.commit()
    flash(f"Student '{student.full_name}' activated.", "success")
    return redirect(url_for("admin_students"))


@app.route("/admin/companies/<int:company_id>/blacklist")
@login_required
def admin_blacklist_company(company_id):
    role_required(UserRole.ADMIN)
    company = Company.query.get_or_404(company_id)
    company.is_blacklisted = True
    company.user.is_active = False
    db.session.commit()
    flash(f"Company '{company.name}' blacklisted.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/companies/<int:company_id>/activate")
@login_required
def admin_activate_company(company_id):
    role_required(UserRole.ADMIN)
    company = Company.query.get_or_404(company_id)
    company.is_blacklisted = False
    company.user.is_active = True
    db.session.commit()
    flash(f"Company '{company.name}' activated.", "success")
    return redirect(url_for("admin_companies"))

@app.route("/admin/applications")
@login_required
def admin_applications():
    role_required(UserRole.ADMIN)
    
    query = request.args.get('q', '').strip().lower()
    applications = Application.query.join(Student).join(PlacementDrive).join(Company)
    
    if query:
        applications = applications.filter(
            db.or_(
                Student.full_name.ilike(f'%{query}%'),
                Company.name.ilike(f'%{query}%')
            )
        )
    
    applications = applications.order_by(Application.applied_at.desc()).all()
    return render_template("admin/applications.html", applications=applications, search_query=query)


@app.route("/admin/companies/<int:company_id>/approve")
@login_required
def admin_approve_company(company_id):
    role_required(UserRole.ADMIN)
    company = Company.query.get_or_404(company_id)
    company.is_approved = True
    db.session.commit()
    flash("Company approved.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/companies/<int:company_id>/reject")
@login_required
def admin_reject_company(company_id):
    role_required(UserRole.ADMIN)
    company = Company.query.get_or_404(company_id)
    company.is_approved = False
    db.session.commit()
    flash("Company marked as not approved.", "info")
    return redirect(url_for("admin_companies"))


@app.route("/admin/students")
@login_required
def admin_students():
    role_required(UserRole.ADMIN)
    
    query = request.args.get('q', '').strip().lower()
    students = Student.query
    
    if query:
        students = students.join(User).filter(
            db.or_(
                Student.full_name.ilike(f'%{query}%'),
                Student.contact.ilike(f'%{query}%'),
                User.username.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            )
        )
    
    students = students.order_by(Student.created_at.desc()).all()
    return render_template("admin/students.html", students=students, search_query=query)


@app.route("/admin/drives")
@login_required
def admin_drives():
    role_required(UserRole.ADMIN)
    drives = PlacementDrive.query.order_by(PlacementDrive.created_at.desc()).all()
    return render_template("admin/drives.html", drives=drives)


@app.route("/admin/drives/<int:drive_id>/approve")
@login_required
def admin_approve_drive(drive_id):
    role_required(UserRole.ADMIN)
    drive = PlacementDrive.query.get_or_404(drive_id)
    drive.status = "approved"
    db.session.commit()
    flash("Drive approved.", "success")
    return redirect(url_for("admin_drives"))


@app.route("/admin/drives/<int:drive_id>/close")
@login_required
def admin_close_drive(drive_id):
    role_required(UserRole.ADMIN)
    drive = PlacementDrive.query.get_or_404(drive_id)
    drive.status = "closed"
    db.session.commit()
    flash("Drive closed.", "info")
    return redirect(url_for("admin_drives"))


# ----------------------------------------------------------------------
# Company views
# ----------------------------------------------------------------------



@app.route("/company/drive/<int:drive_id>/toggle_status")
@login_required
def company_toggle_drive_status(drive_id):
    role_required(UserRole.COMPANY)
    drive = PlacementDrive.query.get_or_404(drive_id)
    
    if drive.company_id != current_user.company.id:
        abort(403)
    
    if drive.status == "active":
        drive.status = "closed"
        flash("Drive closed.", "info")
    elif drive.status == "closed":
        drive.status = "active"
        flash("Drive reopened.", "success")
    else:
        flash("Cannot update pending drive status.", "warning")
    
    db.session.commit()
    return redirect(url_for("company_dashboard"))


@app.route("/company/dashboard")
@login_required
def company_dashboard():
    role_required(UserRole.COMPANY)
    company = current_user.company[0]
    if not company or not company.is_approved:
        flash("Company not approved or blacklisted.", "danger")
        return redirect(url_for("index"))
    
    drives = PlacementDrive.query.filter_by(company_id=company.id).order_by(
        PlacementDrive.created_at.desc()
    ).all()
    
    stats = {
        "total_drives": len(drives),
        "active_drives": len([d for d in drives if d.status == "active"]),
        "applications": Application.query.join(PlacementDrive).filter(
            PlacementDrive.company_id == company.id
        ).count(),
    }
    
    return render_template(
        "company/dashboard.html", 
        company=company, 
        drives=drives, 
        stats=stats
    )


@app.route("/company/create_drive", methods=["GET", "POST"])
@login_required
def company_create_drive():
    role_required(UserRole.COMPANY)
    company = current_user.company[0]
    if not company or not company.is_approved:
        abort(403)

    if request.method == "POST":
        drive = PlacementDrive(
            company_id=company.id,
            title=request.form["title"],
            description=request.form["description"],
            skills_required=request.form.get("skills_required"),
            experience=request.form.get("experience"),
            salary_range=request.form.get("salary_range"),
            eligibility=request.form.get("eligibility"),
            deadline=datetime.strptime(request.form["deadline"], "%Y-%m-%dT%H:%M"),
            status="pending", 
        )
        db.session.add(drive)
        db.session.commit()
        flash("Job posted successfully. Awaiting admin approval.", "success")
        return redirect(url_for("company_dashboard"))

    return render_template("company/create_drive.html")


@app.route("/company/applications")
@login_required
def company_applications():
    role_required(UserRole.COMPANY)
    company = current_user.company[0]
    if not company or not company.is_approved:
        abort(403)

    drive_id = request.args.get("drive", type=int)
    apps_query = Application.query.join(Student).join(PlacementDrive).filter(
        PlacementDrive.company_id == company.id
    )
    
    if drive_id:
        apps_query = apps_query.filter(Application.drive_id == drive_id)
    
    applications = apps_query.order_by(Application.applied_at.desc()).all()
    return render_template("company/applications.html", applications=applications)

@app.route("/company/student/<int:student_id>")
@login_required
def company_student_profile(student_id):
    role_required(UserRole.COMPANY)
    student = Student.query.get_or_404(student_id)
    company = current_user.company[0]
    apps = Application.query.join(PlacementDrive).filter(
        Application.student_id == student.id,
        PlacementDrive.company_id == company.id
    ).all()
    
    return render_template("company/student_profile.html", student=student, applications=apps)


@app.route("/company/application/<int:app_id>/update/<status>")
@login_required
def company_update_application(app_id, status):
    role_required(UserRole.COMPANY)
    company = current_user.company[0]

    if status not in ("applied", "shortlisted", "selected", "rejected"):
        abort(400)

    app_obj = Application.query.get_or_404(app_id)
    if app_obj.drive.company_id != company.id:
        abort(403)
    
    old_status = app_obj.status
    app_obj.status = status
    db.session.commit()
    
    # Simple notification (extendable to email/push later)
    # notification_msg = f"Your application for '{app_obj.drive.title}' has been {status}."
    # flash(notification_msg, "notification")  # Special category for student
    
    # flash(f"Status updated: {old_status|title} → {status|title}", "success")
    return redirect(url_for("company_applications"))



# ----------------------------------------------------------------------
# Student views
# ----------------------------------------------------------------------

@app.route("/student/profile")
@login_required
def student_profile():
    role_required(UserRole.STUDENT)
    student = current_user.student
    if not student:
        flash("No student profile found. Please contact admin.", "danger")
        return redirect(url_for("logout"))
    return render_template("student/profile.html", student=student)

@app.route("/student/edit-profile", methods=["GET", "POST"])
@login_required
def student_update_profile():
    role_required(UserRole.STUDENT)
    student = current_user.student[0]
    
    if not student:
        flash("Profile not found.", "danger")
        return redirect(url_for("logout"))
    
    if request.method == "POST":
        student.full_name = request.form.get("full_name", student.full_name)
        student.contact = request.form.get("contact", student.contact)
        student.branch = request.form.get("branch", student.branch)
        student.year = int(request.form.get("year") or student.year)
        student.cgpa = float(request.form.get("cgpa") or student.cgpa)
        student.skills = request.form.get("skills", student.skills)
        student.education = request.form.get("education", student.education)
        
        if 'resume' in request.files and request.files['resume'].filename:
            resume_file = request.files['resume']
            resume_filename = secure_filename(f"{current_user.username}_{resume_file.filename}")
            resume_path = os.path.join("static", "uploads", "resumes", resume_filename)
            os.makedirs(os.path.dirname(resume_path), exist_ok=True)
            resume_file.save(resume_path)
            student.resume_path = resume_filename
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("student_dashboard"))
    
    return render_template("student/profile_edit.html", student=student)

@app.context_processor
def inject_profile_status():
    def get_profile_status(user):
        if user.role != UserRole.STUDENT:
            return "complete"
        student = user.student[0]
        if not student:
            return "incomplete"
        score = 0
        if student.full_name: score += 1
        if student.branch: score += 1
        if student.skills: score += 1
        if student.resume_path: score += 2
        if score >= 4: return "complete"
        elif score >= 2: return "partial"
        return "incomplete"
    return dict(get_profile_status=get_profile_status)


@app.route("/student/dashboard")
@login_required
def student_dashboard():
    role_required(UserRole.STUDENT)
    student = current_user.student
    if not student:
        return redirect(url_for("student_profile")) 
    
    approved_drives = PlacementDrive.query.filter_by(status="approved").all()
    
    my_apps = []
    if student:
        my_apps = Application.query.filter_by(student_id=student[0].id).order_by(
            Application.applied_at.desc()
        ).all()
    
    return render_template(
        "student/dashboard.html",
        student=student[0],
        approved_drives=approved_drives,
        applications=my_apps,
    )


@app.route("/student/drives")
@login_required
def student_drives():
    role_required(UserRole.STUDENT)
    
    # Search parameters
    query = request.args.get('q', '').strip().lower()
    company_filter = request.args.get('company', '').strip().lower()
    skills_filter = request.args.get('skills', '').strip().lower()
    
    drives = PlacementDrive.query.filter_by(status="approved")
    
    # Multi-field search
    if query:
        drives = drives.filter(
            db.or_(
                PlacementDrive.title.ilike(f'%{query}%'),
                PlacementDrive.company.name.ilike(f'%{query}%'),
                PlacementDrive.skills_required.ilike(f'%{query}%'),
                PlacementDrive.description.ilike(f'%{query}%')
            )
        )
    
    if company_filter:
        drives = drives.join(Company).filter(Company.name.ilike(f'%{company_filter}%'))
    
    if skills_filter:
        drives = drives.filter(PlacementDrive.skills_required.ilike(f'%{skills_filter}%'))
    
    drives = drives.order_by(PlacementDrive.deadline.asc()).all()
    
    return render_template(
        "student/drives.html", 
        drives=drives,
        search_query=query,
        company_filter=company_filter,
        skills_filter=skills_filter
    )



@app.route("/student/apply/<int:drive_id>", methods=["POST"])
@login_required
def student_apply(drive_id):
    role_required(UserRole.STUDENT)
    student = current_user.student[0]

    drive = PlacementDrive.query.get_or_404(drive_id)
    if drive.status != "approved":
        flash("Drive is not open for applications.", "warning")
        return redirect(url_for("student_drives"))

    exists = Application.query.filter_by(student_id=student.id, drive_id=drive_id).first()
    if exists:
        flash("You have already applied for this drive.", "info")
        return redirect(url_for("student_dashboard"))

    app_obj = Application(student_id=student.id, drive_id=drive_id)
    db.session.add(app_obj)
    db.session.commit()
    flash("Application submitted.", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/applications")
@login_required
def student_applications():
    role_required(UserRole.STUDENT)
    student = current_user.student[0]
    if not student:
        flash("Complete your profile first.", "warning")
        return redirect(url_for("student_update_profile"))
    
    status_filter = request.args.get('status', 'all').lower()
    
    apps_query = Application.query.join(PlacementDrive).join(Company).filter(
        Application.student_id == student.id
    ).order_by(Application.applied_at.desc())
    
    if status_filter != 'all':
        apps_query = apps_query.filter(Application.status == status_filter)
    
    applications = apps_query.all()
    
    return render_template(
        "student/applications.html", 
        applications=applications,
        status_filter=status_filter,
        student=student
    )

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # print("Admin login: admin / admin123")
    app.run(debug=True)
