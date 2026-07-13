"""
database.py
------------
Handles all SQLite database operations for the Face Recognition
Attendance System: user accounts (for login), registered people
(students/employees), and attendance logs.
"""

import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_PATH = "attendance.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            rfid_card TEXT UNIQUE,
            qr_code TEXT UNIQUE,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            out_time TEXT,
            FOREIGN KEY (person_id) REFERENCES people (id),
            UNIQUE(person_id, date)
        )
    """)
    conn.commit()

    # ---- Migrations for existing databases ----
    cur.execute("PRAGMA table_info(attendance)")
    att_columns = [row["name"] for row in cur.fetchall()]
    if "out_time" not in att_columns:
        cur.execute("ALTER TABLE attendance ADD COLUMN out_time TEXT")
        conn.commit()

    cur.execute("PRAGMA table_info(people)")
    people_columns = [row["name"] for row in cur.fetchall()]
    if "rfid_card" not in people_columns:
        cur.execute("ALTER TABLE people ADD COLUMN rfid_card TEXT")
        conn.commit()
    if "qr_code" not in people_columns:
        cur.execute("ALTER TABLE people ADD COLUMN qr_code TEXT")
        conn.commit()

    cur.execute("SELECT COUNT(*) as c FROM accounts")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO accounts (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), datetime.now().isoformat()),
        )
        conn.commit()
        print("Default admin account created -> username: admin | password: admin123")

    conn.close()


# ---------------- People (registered faces) ----------------

def add_person(person_code, name, rfid_card=None, qr_code=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO people (person_code, name, rfid_card, qr_code, created_at) VALUES (?, ?, ?, ?, ?)",
        (person_code, name, rfid_card, qr_code, datetime.now().isoformat()),
    )
    conn.commit()
    person_id = cur.lastrowid
    conn.close()
    return person_id


def get_person_by_code(person_code):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE person_code = ?", (person_code,))
    row = cur.fetchone()
    conn.close()
    return row


def get_person_by_id(person_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE id = ?", (person_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_person_by_rfid(rfid_card):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE rfid_card = ?", (rfid_card,))
    row = cur.fetchone()
    conn.close()
    return row


def get_person_by_qr(qr_code):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE qr_code = ?", (qr_code,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_people():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def update_person(person_id, name, rfid_card=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE people SET name = ?, rfid_card = ? WHERE id = ?",
        (name, rfid_card, person_id),
    )
    conn.commit()
    conn.close()


def delete_person(person_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance WHERE person_id = ?", (person_id,))
    cur.execute("DELETE FROM people WHERE id = ?", (person_id,))
    conn.commit()
    conn.close()


# ---------------- Attendance ----------------

def mark_attendance(person_id):
    """
    First scan of the day  -> marks check-in (time), returns ('in', time)
    Second scan same day   -> marks check-out (out_time), returns ('out', time)
    Third+ scan same day   -> already checked in & out, returns ('done', out_time)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM attendance WHERE person_id = ? AND date = ?",
        (person_id, today),
    )
    existing = cur.fetchone()

    if existing is None:
        cur.execute(
            "INSERT INTO attendance (person_id, date, time, out_time) VALUES (?, ?, ?, NULL)",
            (person_id, today, now_time),
        )
        conn.commit()
        conn.close()
        return "in", now_time

    elif existing["out_time"] is None:
        cur.execute(
            "UPDATE attendance SET out_time = ? WHERE id = ?",
            (now_time, existing["id"]),
        )
        conn.commit()
        conn.close()
        return "out", now_time

    else:
        conn.close()
        return "done", existing["out_time"]


def _compute_hours(time_in, time_out):
    if not time_in or not time_out:
        return None
    fmt = "%H:%M:%S"
    t1 = datetime.strptime(time_in, fmt)
    t2 = datetime.strptime(time_out, fmt)
    delta = (t2 - t1).total_seconds() / 3600
    return round(delta, 2)


def get_attendance_by_date(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, p.person_code, p.name, a.date, a.time, a.out_time
        FROM attendance a
        JOIN people p ON a.person_id = p.id
        WHERE a.date = ?
        ORDER BY a.time
    """, (date_str,))
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        row = dict(r)
        row["total_hours"] = _compute_hours(row["time"], row["out_time"])
        result.append(row)
    return result


def get_absentees_by_date(date_str=None):
    """Return list of people who did not mark attendance on a given date
    (defaults to today)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.person_code, p.name
        FROM people p
        WHERE p.id NOT IN (
            SELECT person_id FROM attendance WHERE date = ?
        )
        ORDER BY p.name
    """, (date_str,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_summary_report(start_date, end_date):
    """Summary per person between two dates (inclusive):
    present days, total hours, and attendance percentage."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id AS person_id, p.person_code, p.name,
               COUNT(a.id) as present_days
        FROM people p
        LEFT JOIN attendance a
            ON a.person_id = p.id AND a.date BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY p.name
    """, (start_date, end_date))
    rows = cur.fetchall()

    # total hours per person in the range
    cur.execute("""
        SELECT person_id, time, out_time
        FROM attendance
        WHERE date BETWEEN ? AND ?
    """, (start_date, end_date))
    time_rows = cur.fetchall()
    conn.close()

    hours_by_person = {}
    for r in time_rows:
        h = _compute_hours(r["time"], r["out_time"])
        if h:
            hours_by_person[r["person_id"]] = hours_by_person.get(r["person_id"], 0) + h

    total_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

    result = []
    for r in rows:
        row = dict(r)
        row["total_days"] = total_days
        row["total_hours"] = round(hours_by_person.get(row["person_id"], 0), 2)
        row["attendance_pct"] = round((row["present_days"] / total_days) * 100, 1) if total_days > 0 else 0
        result.append(row)
    return result


def get_person_detail_report(person_id, start_date, end_date):
    """Day-by-day attendance for one person between two dates (inclusive)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, time, out_time
        FROM attendance
        WHERE person_id = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (person_id, start_date, end_date))
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        row = dict(r)
        row["total_hours"] = _compute_hours(row["time"], row["out_time"])
        result.append(row)
    return result


def get_all_attendance():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, p.person_code, p.name, a.date, a.time, a.out_time
        FROM attendance a
        JOIN people p ON a.person_id = p.id
        ORDER BY a.date DESC, a.time DESC
    """)
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        row = dict(r)
        row["total_hours"] = _compute_hours(row["time"], row["out_time"])
        result.append(row)
    return result


# ---------------- Accounts (dashboard login) ----------------

def get_account_by_username(username):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)