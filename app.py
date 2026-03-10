import os
import sqlite3
from datetime import datetime

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

# Optional: quick SQLite sanity check
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

        if role == "student":
            new_user = User(username=username, email=email, role=UserRole.STUDENT, is_active=True)
        else:
            new_user = User(username=username, email=email, role=UserRole.COMPANY, is_active=True)

        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()  # to get new_user.id

        if role == "student":
            student = Student(
                user_id=new_user.id,
                full_name=request.form["full_name"],
                contact=request.form["contact"],
                branch=request.form["branch"],
                year=int(request.form["year"]),
                cgpa=float(request.form["cgpa"] or 0),
            )
            db.session.add(student)
            flash("Student registered. Please log in.", "success")

        else:
            company = Company(
                user_id=new_user.id,
                name=request.form["company_name"],
                hr_contact=request.form["hr_contact"],
                website=request.form["website"],
                address=request.form["address"],
                is_approved=False,
            )
            db.session.add(company)
            flash("Company registered. Await admin approval.", "success")

        db.session.commit()
        return redirect(url_for("login"))

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
    companies = Company.query.order_by(Company.created_at.desc()).all()
    return render_template("admin/companies.html", companies=companies)


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
    students = Student.query.order_by(Student.created_at.desc()).all()
    return render_template("admin/students.html", students=students)


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

@app.route("/company/dashboard")
@login_required
def company_dashboard():
    role_required(UserRole.COMPANY)
    company = current_user.company
    if not company or not company.is_approved:
        flash("Company is not approved yet.", "warning")
        return redirect(url_for("index"))

    drives = PlacementDrive.query.filter_by(company_id=company.id).all()
    applications_count = (
        Application.query.join(PlacementDrive)
        .filter(PlacementDrive.company_id == company.id)
        .count()
    )

    stats = {"drives": len(drives), "applications": applications_count}
    return render_template("company/dashboard.html", company=company, drives=drives, stats=stats)


@app.route("/company/create_drive", methods=["GET", "POST"])
@login_required
def company_create_drive():
    role_required(UserRole.COMPANY)
    company = current_user.company
    if not company or not company.is_approved:
        abort(403)

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        eligibility = request.form["eligibility"]
        deadline_str = request.form["deadline"]  # type="datetime-local"
        deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")

        drive = PlacementDrive(
            company_id=company.id,
            title=title,
            description=description,
            eligibility=eligibility,
            deadline=deadline,
            status="pending",
        )
        db.session.add(drive)
        db.session.commit()
        flash("Placement drive created. Awaiting admin approval.", "success")
        return redirect(url_for("company_dashboard"))

    return render_template("company/create_drive.html")


@app.route("/company/applications")
@login_required
def company_applications():
    role_required(UserRole.COMPANY)
    company = current_user.company
    if not company or not company.is_approved:
        abort(403)

    drive_id = request.args.get("drive", type=int)
    query = (
        Application.query.join(PlacementDrive)
        .filter(PlacementDrive.company_id == company.id)
    )
    if drive_id:
        query = query.filter(Application.drive_id == drive_id)

    applications = query.order_by(Application.applied_at.desc()).all()
    return render_template("company/applications.html", applications=applications)


@app.route("/company/application/<int:app_id>/status/<status>")
@login_required
def company_update_application(app_id, status):
    role_required(UserRole.COMPANY)
    if status not in ("applied", "shortlisted", "selected", "rejected"):
        abort(400)

    app_obj = Application.query.get_or_404(app_id)
    if app_obj.drive.company_id != current_user.company.id:
        abort(403)

    app_obj.status = status
    db.session.commit()
    flash("Application status updated.", "success")
    return redirect(url_for("company_applications"))


# ----------------------------------------------------------------------
# Student views
# ----------------------------------------------------------------------

@app.route("/student/dashboard")
@login_required
def student_dashboard():
    role_required(UserRole.STUDENT)
    student = current_user.student

    approved_drives = PlacementDrive.query.filter_by(status="approved").all()
    my_apps = Application.query.filter_by(student_id=student.id).order_by(
        Application.applied_at.desc()
    ).all()

    return render_template(
        "student/dashboard.html",
        student=student,
        approved_drives=approved_drives,
        applications=my_apps,
    )


@app.route("/student/drives")
@login_required
def student_drives():
    role_required(UserRole.STUDENT)
    drives = PlacementDrive.query.filter_by(status="approved").order_by(
        PlacementDrive.deadline
    ).all()
    return render_template("student/drives.html", drives=drives)


@app.route("/student/apply/<int:drive_id>", methods=["POST"])
@login_required
def student_apply(drive_id):
    role_required(UserRole.STUDENT)
    student = current_user.student

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
    student = current_user.student
    apps = Application.query.filter_by(student_id=student.id).order_by(
        Application.applied_at.desc()
    ).all()
    return render_template("student/applications.html", applications=apps)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

if __name__ == "__main__":
    print("Placement Portal running at http://localhost:5000")
    print("Admin login: admin / admin123")
    app.run(debug=True)
