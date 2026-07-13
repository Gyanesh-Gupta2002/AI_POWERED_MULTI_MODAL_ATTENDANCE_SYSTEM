"""
app.py
-------
Main Flask application for the Face Recognition Attendance System.

Routes:
    /login                          - login page for dashboard access
    /logout                         - log out
    /                                - home / index page
    /register                       - register a new person + capture face samples
    /train                          - (re)train the recognition model
    /person/<id>/edit                - edit a registered person's details
    /person/<id>/delete              - delete a registered person + their records
    /person/<id>/enroll-voice        - record voiceprint for speaker verification
    /qr/<person_code>                - view/download a person's QR code
    /qr-attendance                   - QR-based attendance
    /rfid-attendance                 - RFID-based attendance
    /recognize                       - run live face recognition & mark attendance
    /voice-attendance                - voice-based attendance (with speaker verification)
    /attendance                      - view attendance records
    /dashboard                       - overview: people count, attendance history, absentees
    /export-attendance               - download attendance as CSV
    /export                          - export page (pick date)

NOTE: This app opens the machine's LOCAL webcam (the one attached to the
server/computer running Flask) via OpenCV — it is designed to run on a
single local machine (e.g. a front-desk kiosk PC), not to access a
remote visitor's browser camera. For browser-camera capture you would
additionally need getUserMedia + image upload endpoints.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import check_password_hash
import csv
import io
import os
import qrcode

import database as db
from capture_faces import capture_faces
from train_model import train_model
from recognize import run_recognition
from qr_scan import run_qr_scan
from voice_mark import listen_and_mark
from voice_enroll import enroll_voice
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "change-this-secret-key-in-production"

# ---------------- Attendance Settings ----------------
LATE_CUTOFF_TIME = "11:30:00"  # 24-hour format, change as needed

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class Account(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


@login_manager.user_loader
def load_user(user_id):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return Account(row) if row else None


def generate_qr_image(person_code):
    """Generate and save a QR code PNG for the given person_code."""
    qr_dir = os.path.join("static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{person_code}.png")

    img = qrcode.make(person_code)
    img.save(qr_path)
    return qr_path


# ---------------- Auth ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        account_row = db.get_account_by_username(username)
        if account_row and check_password_hash(account_row["password_hash"], password):
            login_user(Account(account_row))
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------- Core pages ----------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "POST":
        person_code = request.form.get("person_code", "").strip()
        name = request.form.get("name", "").strip()
        rfid_card = request.form.get("rfid_card", "").strip() or None

        if not person_code or not name:
            flash("Person code and name are required.", "error")
            return redirect(url_for("register"))

        if db.get_person_by_code(person_code):
            flash("A person with that code is already registered.", "error")
            return redirect(url_for("register"))

        if rfid_card and db.get_person_by_rfid(rfid_card):
            flash("That RFID card is already assigned to someone else.", "error")
            return redirect(url_for("register"))

        try:
            num_captured = capture_faces(person_code, name)
            # QR code content = person_code itself (kept simple & unique)
            qr_code_value = person_code
            db.add_person(person_code, name, rfid_card=rfid_card, qr_code=qr_code_value)
            generate_qr_image(person_code)
            flash(f"Captured {num_captured} images for {name}. "
                  f"Now click 'Train Model' before recognizing.", "success")
        except Exception as e:
            flash(f"Error capturing faces: {e}", "error")

        return redirect(url_for("register"))

    people = db.get_all_people()
    return render_template("register.html", people=people)


@app.route("/train", methods=["POST"])
@login_required
def train():
    try:
        train_model()
        flash("Model trained successfully.", "success")
    except Exception as e:
        flash(f"Training failed: {e}", "error")
    return redirect(url_for("register"))


@app.route("/person/<int:person_id>/edit", methods=["GET", "POST"])
@login_required
def edit_person(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for("register"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rfid_card = request.form.get("rfid_card", "").strip() or None

        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("edit_person", person_id=person_id))

        db.update_person(person_id, name, rfid_card)
        flash(f"Updated details for {name}.", "success")
        return redirect(url_for("register"))

    return render_template("edit_person.html", person=person)


@app.route("/person/<int:person_id>/delete", methods=["POST"])
@login_required
def delete_person(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for("register"))

    name = person["name"]
    db.delete_person(person_id)
    flash(f"{name} and their attendance records have been deleted.", "success")
    return redirect(url_for("register"))


@app.route("/person/<int:person_id>/enroll-voice", methods=["POST"])
@login_required
def enroll_person_voice(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for("register"))
    try:
        enroll_voice(person["person_code"], person["name"])
        flash(f"Voice enrolled for {person['name']}.", "success")
    except Exception as e:
        flash(f"Voice enrollment failed: {e}", "error")
    return redirect(url_for("register"))


@app.route("/qr/<person_code>")
@login_required
def view_qr(person_code):
    qr_path = os.path.join("static", "qrcodes", f"{person_code}.png")
    if not os.path.exists(qr_path):
        generate_qr_image(person_code)
    return render_template("view_qr.html", person_code=person_code)


@app.route("/qr-attendance", methods=["GET", "POST"])
@login_required
def qr_attendance():
    marked = []
    if request.method == "POST":
        try:
            marked = run_qr_scan()
            flash(f"QR scan session ended. Marked {len(marked)} people.", "success")
        except Exception as e:
            flash(f"QR scan failed: {e}", "error")
    return render_template(
        "qr_attendance.html",
        marked=marked,
        records=db.get_attendance_by_date(),
        cutoff=LATE_CUTOFF_TIME
    )


@app.route("/rfid-attendance", methods=["GET", "POST"])
@login_required
def rfid_attendance():
    marked = []
    if request.method == "POST":
        card_number = request.form.get("rfid_input", "").strip()

        if not card_number:
            flash("No card number received. Try scanning again.", "error")
        else:
            person = db.get_person_by_rfid(card_number)
            if not person:
                flash("No person found for this RFID card.", "error")
            else:
                action, _ = db.mark_attendance(person["id"])
                if action == "in":
                    flash(f"{person['name']} checked in successfully.", "success")
                elif action == "out":
                    flash(f"{person['name']} checked out successfully.", "success")
                else:
                    flash(f"{person['name']} already checked in and out today.", "info")

    return render_template(
        "rfid_attendance.html",
        records=db.get_attendance_by_date(),
        cutoff=LATE_CUTOFF_TIME
    )


@app.route("/recognize", methods=["GET", "POST"])
@login_required
def recognize():
    marked = []
    if request.method == "POST":
        try:
            marked = run_recognition()
            flash(f"Recognition session ended. Marked {len(marked)} people present.", "success")
        except Exception as e:
            flash(f"Recognition failed: {e}", "error")
    return render_template("attendance.html", marked=marked, records=db.get_attendance_by_date(), cutoff=LATE_CUTOFF_TIME)


@app.route("/voice-attendance", methods=["GET", "POST"])
@login_required
def voice_attendance():
    marked = []
    if request.method == "POST":
        person, status = listen_and_mark()

        if status == "marked_in":
            flash(f"{person['name']} checked in successfully.", "success")
        elif status == "marked_out":
            flash(f"{person['name']} checked out successfully.", "success")
        elif status == "already_done":
            flash(f"{person['name']} already checked in and out today.", "info")
        elif status == "voice_mismatch":
            flash(f"Voice does not match {person['name']}'s registered voice. Attendance denied.", "error")
        elif status == "no_voiceprint":
            flash(f"{person['name']} has no voice profile enrolled yet. Please enroll first.", "error")
        elif status == "no_match":
            flash("Could not match the spoken name to any registered person.", "error")
        elif status == "not_understood":
            flash("Could not understand speech. Please try again.", "error")
        elif status == "timeout":
            flash("No speech detected in time.", "error")
        else:
            flash("Speech service unavailable. Check your internet connection.", "error")

    return render_template("attendance.html", marked=marked, records=db.get_attendance_by_date(), cutoff=LATE_CUTOFF_TIME, mode="voice")


@app.route("/attendance")
@login_required
def attendance():
    date_filter = request.args.get("date")
    records = db.get_attendance_by_date(date_filter) if date_filter else db.get_all_attendance()
    absentees = db.get_absentees_by_date(date_filter) if date_filter else db.get_absentees_by_date()
    return render_template("attendance.html", records=records, marked=[], cutoff=LATE_CUTOFF_TIME, absentees=absentees)


@app.route("/dashboard")
@login_required
def dashboard():
    people = db.get_all_people()
    todays_attendance = db.get_attendance_by_date()
    absentees = db.get_absentees_by_date()
    return render_template(
        "dashboard.html",
        people_count=len(people),
        people=people,
        todays_attendance=todays_attendance,
        absentees=absentees,
        cutoff=LATE_CUTOFF_TIME
    )


@app.route("/export-attendance")
@login_required
def export_attendance():
    date_filter = request.args.get("date")
    records = db.get_attendance_by_date(date_filter) if date_filter else db.get_all_attendance()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Code", "Name", "Date", "Time"])

    for r in records:
        writer.writerow([r["person_code"], r["name"], r["date"], r["time"]])

    csv_data = output.getvalue()
    output.close()

    filename = f"attendance_{date_filter}.csv" if date_filter else "attendance_all.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/reports")
@login_required
def reports():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not start_date or not end_date:
        # default to current month so far
        today = datetime.now()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    summary = db.get_summary_report(start_date, end_date)

    return render_template(
        "reports.html",
        summary=summary,
        start_date=start_date,
        end_date=end_date
    )


@app.route("/reports/person/<int:person_id>")
@login_required
def report_person(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for("reports"))

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    records = db.get_person_detail_report(person_id, start_date, end_date)

    return render_template(
        "report_person.html",
        person=person,
        records=records,
        start_date=start_date,
        end_date=end_date
    )


@app.route("/export")
@login_required
def export_page():
    return render_template("export.html")


# ---------------- JSON API (optional, handy for AJAX/testing) ----------------

@app.route("/api/attendance/today")
@login_required
def api_attendance_today():
    records = db.get_attendance_by_date()
    return jsonify([dict(r) for r in records])


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)