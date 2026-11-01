from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session, abort, Response
)
import csv
import io
import sqlite3
import os
import secrets
from functools import wraps
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Replace this with a long, random secret before deployment.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "hall.db")

# Set these environment variables before deployment.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# Change this to the actual approved hall rental amount.
HALL_PRICE = 10000
MAX_GUESTS = 1000
CAPACITY_TIER_SIZE = 250
CAPACITY_TIER_INCREMENT = 5000
VEGETARIAN_CATERING_PER_GUEST = 250
PAYMENT_METHODS = {"UPI", "Cash", "Bank transfer"}
EVENT_TYPES = (
    "Wedding", "Reception", "Engagement", "Birthday", "Anniversary",
    "Religious Ceremony", "Community Event", "Conference / Meeting", "Other"
)


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                event_type TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                guests INTEGER NOT NULL,
                address TEXT,
                notes TEXT,
                hall_package TEXT NOT NULL DEFAULT 'Community Hall',
                catering_option TEXT NOT NULL DEFAULT 'Not required',
                decoration_option TEXT NOT NULL DEFAULT 'Not required',
                seating_layout TEXT NOT NULL DEFAULT 'Not specified',
                preferred_payment_method TEXT NOT NULL DEFAULT 'UPI',
                payment_method TEXT NOT NULL DEFAULT '',
                payment_reference TEXT NOT NULL DEFAULT '',
                amount_paid INTEGER NOT NULL DEFAULT 0,
                hall_amount INTEGER NOT NULL DEFAULT 10000,
                catering_amount INTEGER NOT NULL DEFAULT 0,
                amount INTEGER NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_booking_date
            ON bookings(booking_date)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_booking_status
            ON bookings(status)
        """)

        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(bookings)")
        }
        new_columns = {
            "hall_package": "TEXT NOT NULL DEFAULT 'Community Hall'",
            "catering_option": "TEXT NOT NULL DEFAULT 'Not required'",
            "decoration_option": "TEXT NOT NULL DEFAULT 'Not required'",
            "seating_layout": "TEXT NOT NULL DEFAULT 'Not specified'",
            "preferred_payment_method": "TEXT NOT NULL DEFAULT 'UPI'",
            "payment_method": "TEXT NOT NULL DEFAULT ''",
            "payment_reference": "TEXT NOT NULL DEFAULT ''",
            "amount_paid": "INTEGER NOT NULL DEFAULT 0",
            "hall_amount": "INTEGER NOT NULL DEFAULT 10000",
            "catering_amount": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in new_columns.items():
            if column not in existing_columns:
                conn.execute(
                    f"ALTER TABLE bookings ADD COLUMN {column} {definition}"
                )


def find_slot_conflict(conn, booking_date, start_time, end_time):
        return conn.execute("""
                SELECT id FROM bookings
                WHERE booking_date = ?
                    AND status IN ('Pending', 'Approved')
                    AND start_time < ?
                    AND end_time > ?
                LIMIT 1
        """, (booking_date, end_time, start_time)).fetchone()


def calculate_quote(guests, catering_option):
    hall_amount = HALL_PRICE + (
        (guests - 1) // CAPACITY_TIER_SIZE
    ) * CAPACITY_TIER_INCREMENT
    catering_amount = (
        guests * VEGETARIAN_CATERING_PER_GUEST
        if catering_option == "Vegetarian catering"
        else 0
    )
    return hall_amount, catering_amount, hall_amount + catering_amount


def admin_account_exists():
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM admin_accounts LIMIT 1"
        ).fetchone() is not None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Please log in as an administrator.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def home():
    with get_db() as conn:
        total = conn.execute("""
            SELECT COUNT(*) AS count
            FROM bookings
            WHERE status = 'Approved'
        """).fetchone()["count"]

    return render_template(
        "index.html",
        hall_price=HALL_PRICE,
        approved_bookings=total
    )


@app.route("/availability")
def availability():
    booking_date = request.args.get("booking_date", "")
    start_time = request.args.get("start_time", "")
    end_time = request.args.get("end_time", "")
    event_type = request.args.get("event_type", "")
    checked = bool(request.args)
    is_available = None
    error = None

    if checked:
        try:
            date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
            start_obj = datetime.strptime(start_time, "%H:%M").time()
            end_obj = datetime.strptime(end_time, "%H:%M").time()
        except ValueError:
            error = "Choose an event, date, start time, and end time."
        else:
            if event_type not in EVENT_TYPES:
                error = "Choose a valid event type."
            elif date_obj < datetime.now().date():
                error = "Choose today or a future date."
            elif end_obj <= start_obj:
                error = "End time must be later than start time."
            else:
                with get_db() as conn:
                    is_available = find_slot_conflict(
                        conn, booking_date, start_time, end_time
                    ) is None

    return render_template(
        "availability.html",
        today=datetime.now().strftime("%Y-%m-%d"),
        event_types=EVENT_TYPES,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        checked=checked,
        is_available=is_available,
        error=error
    )


@app.route("/book", methods=["GET", "POST"])
def book():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        event_type = request.form.get("event_type", "").strip()
        booking_date = request.form.get("booking_date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        hall_package = request.form.get("hall_package", "").strip()
        catering_option = request.form.get("catering_option", "").strip()
        decoration_option = request.form.get("decoration_option", "").strip()
        seating_layout = request.form.get("seating_layout", "").strip()
        preferred_payment_method = request.form.get(
            "preferred_payment_method", ""
        ).strip()

        try:
            guests = int(request.form.get("guests", "0"))
            date_obj = datetime.strptime(
                booking_date, "%Y-%m-%d"
            ).date()

            start_obj = datetime.strptime(
                start_time, "%H:%M"
            ).time()

            end_obj = datetime.strptime(
                end_time, "%H:%M"
            ).time()

        except (ValueError, TypeError):
            flash("Please enter valid booking details.", "error")
            return redirect(url_for("book"))

        if not name or not phone or event_type not in EVENT_TYPES:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("book"))

        if (
            hall_package != "Community Hall"
            or catering_option not in {
                "Not required", "Vegetarian catering", "Discuss with management"
            }
            or decoration_option not in {
                "Not required", "Basic decoration", "Custom decoration"
            }
            or seating_layout not in {
                "Not specified", "Theatre", "Banquet", "Traditional", "Other"
            }
            or preferred_payment_method not in PAYMENT_METHODS
        ):
            flash("Please choose valid event and payment options.", "error")
            return redirect(url_for("book"))

        if not phone.isdigit() or len(phone) != 10:
            flash("Enter a valid 10-digit mobile number.", "error")
            return redirect(url_for("book"))

        if not (1 <= guests <= MAX_GUESTS):
            flash(
                f"Guest count must be between 1 and {MAX_GUESTS:,}.",
                "error"
            )
            return redirect(url_for("book"))

        if date_obj < datetime.now().date():
            flash("Please choose today or a future date.", "error")
            return redirect(url_for("book"))

        if end_obj <= start_obj:
            flash("End time must be later than start time.", "error")
            return redirect(url_for("book"))

        hall_amount, catering_amount, amount = calculate_quote(
            guests, catering_option
        )

        with get_db() as conn:
            conflict = find_slot_conflict(
                conn, booking_date, start_time, end_time
            )

            if conflict:
                flash(
                    "This time slot is already reserved or awaiting "
                    "approval. Please select another time.",
                    "error"
                )
                return redirect(url_for("book"))

            booking_code = (
                "SMH" + secrets.token_hex(4).upper()
            )

            conn.execute("""
                INSERT INTO bookings (
                    booking_code, name, phone, email,
                    event_type, booking_date,
                    start_time, end_time, guests,
                    address, notes, hall_package,
                    catering_option, decoration_option, seating_layout,
                    preferred_payment_method, amount_paid,
                    hall_amount, catering_amount, amount,
                    payment_status, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        0, ?, ?, ?, 'Unpaid', 'Pending', ?)
            """, (
                booking_code,
                name,
                phone,
                email,
                event_type,
                booking_date,
                start_time,
                end_time,
                guests,
                address,
                notes,
                hall_package,
                catering_option,
                decoration_option,
                seating_layout,
                preferred_payment_method,
                hall_amount,
                catering_amount,
                amount,
                datetime.now().isoformat(timespec="seconds")
            ))

        return redirect(
            url_for("confirmation", code=booking_code)
        )

    return render_template(
        "book.html",
        hall_price=HALL_PRICE,
        max_guests=MAX_GUESTS,
        capacity_tier_size=CAPACITY_TIER_SIZE,
        capacity_tier_increment=CAPACITY_TIER_INCREMENT,
        catering_rate=VEGETARIAN_CATERING_PER_GUEST,
        today=datetime.now().strftime("%Y-%m-%d"),
        event_types=EVENT_TYPES,
        booking_values=request.args
    )


@app.route("/confirmation/<code>")
def confirmation(code):
    with get_db() as conn:
        booking = conn.execute("""
            SELECT * FROM bookings
            WHERE booking_code = ?
        """, (code,)).fetchone()

    if not booking:
        abort(404)

    return render_template(
        "confirmation.html",
        booking=booking
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not admin_account_exists() and not ADMIN_PASSWORD:
        return redirect(url_for("admin_setup"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db() as conn:
            account = conn.execute(
                "SELECT * FROM admin_accounts WHERE username = ?",
                (username,)
            ).fetchone()

        database_login = (
            account is not None
            and check_password_hash(account["password_hash"], password)
        )
        environment_login = (
            ADMIN_PASSWORD
            and secrets.compare_digest(username, ADMIN_USERNAME)
            and secrets.compare_digest(password, ADMIN_PASSWORD)
        )

        if database_login or environment_login:
            session.clear()
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template(
        "admin_login.html",
        setup_available=not admin_account_exists()
    )


@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    if admin_account_exists():
        flash("Administrator setup is already complete. Please sign in.", "error")
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(username) < 3 or len(username) > 50:
            flash("Username must be between 3 and 50 characters.", "error")
        elif not all(char.isalnum() or char in "._-" for char in username):
            flash("Username may contain letters, numbers, dots, dashes, and underscores.", "error")
        elif len(password) < 12:
            flash("Password must be at least 12 characters long.", "error")
        elif password != confirm_password:
            flash("The password confirmation does not match.", "error")
        else:
            try:
                with get_db() as conn:
                    conn.execute("""
                        INSERT INTO admin_accounts (
                            username, password_hash, created_at
                        ) VALUES (?, ?, ?)
                    """, (
                        username,
                        generate_password_hash(password),
                        datetime.now().isoformat(timespec="seconds")
                    ))
            except sqlite3.IntegrityError:
                flash("Administrator setup has already been completed.", "error")
                return redirect(url_for("admin_login"))

            session.clear()
            session["admin"] = username
            flash("Administrator account created. You are now signed in.", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template("admin_setup.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    allowed_statuses = [
        "Pending", "Approved", "Rejected", "Cancelled"
    ]

    query = "SELECT * FROM bookings WHERE 1=1"
    params = []

    if search:
        term = "%" + search + "%"
        query += """
            AND (
                booking_code LIKE ?
                OR name LIKE ?
                OR phone LIKE ?
            )
        """
        params.extend([term, term, term])

    if status_filter in allowed_statuses:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY booking_date DESC, start_time DESC"

    with get_db() as conn:
        bookings = conn.execute(query, params).fetchall()

        counts = {}
        for status in allowed_statuses:
            counts[status] = conn.execute(
                "SELECT COUNT(*) FROM bookings WHERE status = ?",
                (status,)
            ).fetchone()[0]

    return render_template(
        "admin_dashboard.html",
        bookings=bookings,
        counts=counts,
        search=search,
        status_filter=status_filter
    )


@app.route("/admin/export.csv")
@admin_required
def export_bookings():
    with get_db() as conn:
        bookings = conn.execute(
            "SELECT * FROM bookings ORDER BY booking_date, start_time"
        ).fetchall()

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = [
        "booking_code", "name", "phone", "email", "event_type",
        "booking_date", "start_time", "end_time", "guests", "address",
        "notes", "hall_package", "catering_option", "decoration_option",
        "seating_layout", "preferred_payment_method", "payment_method",
        "payment_reference", "amount_paid", "hall_amount",
        "catering_amount", "amount", "payment_status", "status",
        "created_at"
    ]
    writer.writerow(columns)
    writer.writerows(
        [booking[column] for column in columns]
        for booking in bookings
    )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hall-bookings.csv"}
    )


@app.route("/admin/payment/<int:booking_id>", methods=["POST"])
@admin_required
def update_payment(booking_id):
    try:
        amount_paid = int(request.form.get("amount_paid", ""))
    except (ValueError, TypeError):
        flash("Enter a valid payment amount.", "error")
        return redirect(url_for("admin_dashboard"))

    payment_method = request.form.get("payment_method", "").strip()
    payment_reference = request.form.get("payment_reference", "").strip()

    with get_db() as conn:
        booking = conn.execute(
            "SELECT amount FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if not booking:
            abort(404)

        if not 0 <= amount_paid <= booking["amount"]:
            flash("Paid amount must be between zero and the booking total.", "error")
            return redirect(url_for("admin_dashboard"))

        if amount_paid and payment_method not in PAYMENT_METHODS:
            flash("Choose a valid payment method for the recorded payment.", "error")
            return redirect(url_for("admin_dashboard"))

        if amount_paid == 0:
            payment_status = "Unpaid"
            payment_method = ""
            payment_reference = ""
        elif amount_paid == booking["amount"]:
            payment_status = "Paid"
        else:
            payment_status = "Partially Paid"

        conn.execute("""
            UPDATE bookings
            SET amount_paid = ?, payment_status = ?,
                payment_method = ?, payment_reference = ?
            WHERE id = ?
        """, (
            amount_paid,
            payment_status,
            payment_method,
            payment_reference[:100],
            booking_id
        ))

    flash("Payment record updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/update/<int:booking_id>", methods=["POST"])
@admin_required
def update_booking(booking_id):
    new_status = request.form.get("status", "")

    allowed_statuses = {
        "Pending", "Approved", "Rejected", "Cancelled"
    }

    if new_status not in allowed_statuses:
        flash("Invalid booking status.", "error")
        return redirect(url_for("admin_dashboard"))

    with get_db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if not booking:
            abort(404)

        if new_status == "Approved":
            conflict = conn.execute("""
                SELECT id FROM bookings
                WHERE booking_date = ?
                                    AND status IN ('Pending', 'Approved')
                  AND id != ?
                  AND start_time < ?
                  AND end_time > ?
                LIMIT 1
            """, (
                booking["booking_date"],
                booking_id,
                booking["end_time"],
                booking["start_time"]
            )).fetchone()

            if conflict:
                flash(
                    "Cannot approve: another booking occupies "
                    "this time slot.",
                    "error"
                )
                return redirect(url_for("admin_dashboard"))

        conn.execute("""
            UPDATE bookings
            SET status = ?
            WHERE id = ?
        """, (new_status, booking_id))

    flash("Booking status updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(404)
def not_found(error):
    return "<h1>404 - Page not found</h1>", 404


init_db()

if __name__ == "__main__":
    app.run(debug=True)