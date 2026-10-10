from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from functools import wraps
from datetime import datetime
from io import BytesIO
import os
import secrets
import smtplib
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from openpyxl import Workbook

from storage import (
    init_db, verify_login,
    get_users, add_user, update_user, delete_user,
    get_user_profile, update_user_profile,
    insert_inspection, get_all_inspections,
    update_inspection, delete_inspection,
    get_user_entry_counts, get_today_entries_summary,
    get_admin_emails, get_monthly_counts
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

HEADERS = ["Sl No", "Name", "Phone No", "Mail ID",
           "Vehicle Type", "Vehicle No", "Date of Inspection",
           "Date of Expiry", "Entered By"]


# ================= EMAIL CONFIG =================
EMAIL_CONFIG = {
    "enabled": os.environ.get("EMAIL_ENABLED", "true").lower() == "true",
    "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
    "smtp_user": os.environ.get("SMTP_USER", ""),
    "smtp_pass": os.environ.get("SMTP_PASS", ""),
    "from_addr": os.environ.get("SMTP_FROM", ""),
    "subject": os.environ.get("DAILY_EMAIL_SUBJECT", "CNG Tool - Daily Entry Summary"),
    "monthly_subject": os.environ.get("MONTHLY_EMAIL_SUBJECT", "CNG Tool - Monthly Report")
}


def app_today():
    timezone = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))
    return datetime.now(timezone).date()


# ================= EXCEL =================
def build_month_excel(rows, year, month):
    wb = Workbook()
    ws = wb.active
    ws.title = f"{year}-{month:02d}"
    ws.append(HEADERS)
    idx = 1
    for r in rows:
        d = r[6]
        if d.year == year and d.month == month:
            ws.append([idx, r[1], r[2], r[3], r[4] or "", r[5] or "",
                       str(r[6]), str(r[7]), r[8] or ""])
            idx += 1
    return wb


# ================= EMAIL HELPERS =================
def _html_table_header():
    return ("<tr style='background:#eef2fb;'>"
            "<th>Sl</th><th>Name</th><th>Phone</th><th>Mail ID</th>"
            "<th>Vehicle Type</th><th>Vehicle No</th>"
            "<th>Inspection Date</th><th>Expiry Date</th>"
            "<th>Entered By</th></tr>")


def _row_to_html(idx, r):
    return (
        "<tr>"
        f"<td align='center'>{idx}</td>"
        f"<td>{r[1] or ''}</td>"
        f"<td>{r[2] or ''}</td>"
        f"<td>{r[3] or ''}</td>"
        f"<td>{r[4] or ''}</td>"
        f"<td>{r[5] or ''}</td>"
        f"<td>{r[6]}</td>"
        f"<td>{r[7]}</td>"
        f"<td>{r[8] or ''}</td>"
        "</tr>"
    )


def _send_email(to_addr, subject, body_html,
                attachment_path=None, attachment_name=None):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = EMAIL_CONFIG["from_addr"] or EMAIL_CONFIG["smtp_user"]
    msg["To"] = to_addr

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_html, "html"))
    msg.attach(alt)

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(
                f.read(),
                _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        part.add_header("Content-Disposition", "attachment",
                        filename=attachment_name)
        msg.attach(part)

    with smtplib.SMTP(
        EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"], timeout=30
    ) as s:
        s.starttls()
        s.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_pass"])
        s.sendmail(msg["From"], [to_addr], msg.as_string())


# ================= DAILY EMAIL =================
def send_daily_email(report_date=None):
    if not EMAIL_CONFIG["enabled"]:
        raise RuntimeError("Email reports are disabled")
    if not EMAIL_CONFIG["smtp_user"] or not EMAIL_CONFIG["smtp_pass"]:
        raise RuntimeError("SMTP credentials are not configured")

    today = (report_date or app_today()).isoformat()
    summary = get_today_entries_summary(today)
    admins = get_admin_emails()
    if not admins:
        raise RuntimeError("No admin email addresses are configured")

    total_today = sum(summary.values())

    html = ["<html><body style='font-family:Arial,sans-serif;color:#222;'>"]
    html.append(f"<h2 style='color:#1e3c72;'>CNG Tool - Daily Summary for {today}</h2>")
    html.append(f"<p><b>Total entries today:</b> {total_today}</p>")

    if summary:
        html.append("<h3 style='color:#1e3c72;margin-top:16px;'>Entries per User</h3>")
        html.append("<table border='1' cellpadding='8' cellspacing='0' "
                    "style='border-collapse:collapse;font-size:13px;'>")
        html.append("<tr style='background:#eef2fb;'><th>User</th><th>Entries</th></tr>")
        for user, cnt in summary.items():
            html.append(f"<tr><td>{user}</td><td align='center'>{cnt}</td></tr>")
        html.append("</table>")
    else:
        html.append("<p>No entries were added today.</p>")

    html.append("<p style='color:#888;font-size:11px;margin-top:20px;'>"
                "The monthly report with the Excel file is sent on the last "
                "day of the month.</p></body></html>")

    body = "".join(html)
    print(f"[mail] Sending daily summary to {len(admins)} admin(s): {[a[1] for a in admins]}")

    failures = []
    for username, to_addr in admins:
        try:
            _send_email(
                to_addr,
                f"{EMAIL_CONFIG['subject']} - {today}",
                body,
                None,
                None
            )
            print(f"[mail] OK Daily summary -> '{username}' <{to_addr}>")
        except Exception as e:
            print(f"[mail] FAIL Daily for '{username}' <{to_addr}>: {e}")
            failures.append(username)
    if failures:
        raise RuntimeError(
            f"Daily report failed for {len(failures)} admin recipient(s)"
        )


# ================= MONTHLY EMAIL =================
def send_monthly_email(year, month):
    if not EMAIL_CONFIG["enabled"]:
        raise RuntimeError("Email reports are disabled")
    if not EMAIL_CONFIG["smtp_user"] or not EMAIL_CONFIG["smtp_pass"]:
        raise RuntimeError("SMTP credentials are not configured")

    admins = get_admin_emails()
    if not admins:
        raise RuntimeError("No admin email addresses are configured")

    rows = get_all_inspections()
    in_month = [r for r in rows if r[6].year == year and r[6].month == month]
    total = len(in_month)

    per_user = {}
    for r in in_month:
        u = r[8] or "(unknown)"
        per_user[u] = per_user.get(u, 0) + 1
    per_user = dict(sorted(per_user.items(), key=lambda x: (-x[1], x[0])))

    tmp_path = os.path.join(
        os.environ.get("TMPDIR", os.environ.get("TEMP", "/tmp")),
        f"inspections_{year}-{month:02d}.xlsx"
    )
    wb = build_month_excel(rows, year, month)
    wb.save(tmp_path)

    html = ["<html><body style='font-family:Arial,sans-serif;color:#222;'>"]
    html.append(f"<h2 style='color:#1e3c72;'>CNG Tool - Monthly Report "
                f"({year}-{month:02d})</h2>")
    html.append(f"<p><b>Total entries this month:</b> {total}</p>")

    if per_user:
        html.append("<h3 style='color:#1e3c72;margin-top:16px;'>Entries per User</h3>")
        html.append("<table border='1' cellpadding='8' cellspacing='0' "
                    "style='border-collapse:collapse;font-size:13px;'>")
        html.append("<tr style='background:#eef2fb;'><th>User</th><th>Entries</th></tr>")
        for user, cnt in per_user.items():
            html.append(f"<tr><td>{user}</td><td align='center'>{cnt}</td></tr>")
        html.append("</table>")
    else:
        html.append("<p>No entries this month.</p>")

    if in_month:
        html.append("<h3 style='color:#1e3c72;margin-top:24px;'>All Records (this month)</h3>")
        html.append("<table border='1' cellpadding='6' cellspacing='0' "
                    "style='border-collapse:collapse;font-size:12px;'>")
        html.append(_html_table_header())
        for i, r in enumerate(in_month, start=1):
            html.append(_row_to_html(i, r))
        html.append("</table>")

    html.append("<p style='color:#888;font-size:11px;margin-top:20px;'>"
                "Monthly Excel attached (only this month's records).</p></body></html>")

    body = "".join(html)
    print(f"[mail] Sending monthly report to {len(admins)} admin(s): {[a[1] for a in admins]}")

    failures = []
    for username, to_addr in admins:
        try:
            _send_email(
                to_addr,
                f"{EMAIL_CONFIG['monthly_subject']} - {year}-{month:02d}",
                body,
                tmp_path,
                f"inspections_{year}-{month:02d}.xlsx"
            )
            print(f"[mail] OK Monthly report -> '{username}' <{to_addr}>")
        except Exception as e:
            print(f"[mail] FAIL Monthly for '{username}' <{to_addr}>: {e}")
            failures.append(username)
    try:
        os.remove(tmp_path)
    except OSError as e:
        print(f"[mail] Could not remove temporary report: {e}")
    if failures:
        raise RuntimeError(
            f"Monthly report failed for {len(failures)} admin recipient(s)"
        )


# ================= AUTH =================
def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return jsonify({"ok": False, "msg": "Not logged in"}), 401
            if role and session.get("role") != role:
                return jsonify({"ok": False, "msg": "Forbidden"}), 403
            return fn(*a, **kw)
        return wrapper
    return decorator


# ================= PAGES =================
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))
    if session["role"] == "admin":
        return render_template("admin.html", user=session["username"])
    return render_template("user.html", user=session["username"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ================= AUTH API =================
@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "msg": "Enter username and password"}), 400
    row = verify_login(username, password)
    if not row:
        return jsonify({"ok": False, "msg": "Invalid username or password"}), 401
    session["user_id"] = row[0]
    session["username"] = row[1]
    session["role"] = row[2]
    return jsonify({"ok": True, "role": row[2]})


# ================= PROFILE =================
@app.route("/api/profile", methods=["GET"])
@login_required()
def api_profile_get():
    row = get_user_profile(session["user_id"])
    if not row:
        return jsonify({"ok": False, "msg": "User not found"}), 404
    return jsonify({
        "ok": True,
        "data": {
            "id": row[0], "username": row[1], "role": row[2],
            "full_name": row[3] or "",
            "phone": row[4] or "",
            "email": row[5] or ""
        }
    })


@app.route("/api/profile", methods=["POST"])
@login_required()
def api_profile_save():
    d = request.get_json() or {}
    update_user_profile(
        session["user_id"],
        (d.get("full_name") or "").strip(),
        (d.get("phone") or "").strip(),
        (d.get("email") or "").strip(),
    )
    return jsonify({"ok": True})


# ================= USER MANAGEMENT =================
@app.route("/api/users", methods=["GET"])
@login_required(role="admin")
def api_users_list():
    rows = get_users()
    return jsonify({
        "ok": True,
        "data": [{
            "id": r[0],
            "username": r[1],
            "role": r[2]
        } for r in rows]
    })


@app.route("/api/users/add", methods=["POST"])
@login_required(role="admin")
def api_users_add():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    role = d.get("role") or "user"
    if not username or not password:
        return jsonify({"ok": False, "msg": "Username and password required"}), 400
    if role not in ("admin", "user"):
        role = "user"
    new_id, err = add_user(username, password, role)
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/users/update", methods=["POST"])
@login_required(role="admin")
def api_users_update():
    d = request.get_json() or {}
    uid = d.get("id")
    if not uid:
        return jsonify({"ok": False, "msg": "Missing id"}), 400
    ok, err = update_user(
        int(uid),
        username=(d.get("username") or "").strip() or None,
        password=d.get("password") or None,
        role=d.get("role") or None,
    )
    if not ok:
        return jsonify({"ok": False, "msg": err}), 400
    return jsonify({"ok": True})


@app.route("/api/users/delete", methods=["POST"])
@login_required(role="admin")
def api_users_delete():
    d = request.get_json() or {}
    uid = d.get("id")
    if not uid:
        return jsonify({"ok": False, "msg": "Missing id"}), 400
    ok, err = delete_user(int(uid))
    if not ok:
        return jsonify({"ok": False, "msg": err}), 400
    return jsonify({"ok": True})


@app.route("/api/users/entry-counts", methods=["GET"])
@login_required(role="admin")
def api_users_entry_counts():
    from_date = request.args.get("from_date") or None
    to_date = request.args.get("to_date") or None
    data = get_user_entry_counts(from_date, to_date)
    return jsonify({"ok": True, "data": data})


# ================= INSPECTIONS =================
@app.route("/api/save", methods=["POST"])
@login_required()
def api_save():
    d = request.get_json() or {}
    name = (d.get("name") or "").strip()
    phone = (d.get("phone") or "").strip()
    email = (d.get("email") or "").strip()
    vehicle_type = (d.get("vehicle_type") or "").strip()
    vehicle_no = (d.get("vehicle_no") or "").strip()
    insp = d.get("inspection_date")
    exp = d.get("expiry_date")

    if not (name and phone and insp and exp):
        return jsonify({"ok": False, "msg": "Please fill all required fields"}), 400

    new_id = insert_inspection(name, phone, email, vehicle_type, vehicle_no,
                               insp, exp, session["username"])
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/excel-view", methods=["GET"])
@login_required()
def api_excel_view():
    from_date = request.args.get("from_date") or ""
    to_date = request.args.get("to_date") or ""
    q = (request.args.get("q") or "").strip().lower()

    rows = get_all_inspections()
    data = []
    for i, r in enumerate(rows, start=1):
        insp = str(r[6])
        if from_date and insp < from_date:
            continue
        if to_date and insp > to_date:
            continue
        if q:
            haystack = " ".join([
                str(r[1] or ""), str(r[2] or ""), str(r[3] or ""),
                str(r[4] or ""), str(r[5] or ""), str(r[8] or ""),
            ]).lower()
            if q not in haystack:
                continue
        data.append({
            "sl": i, "id": r[0], "name": r[1], "phone": r[2],
            "email": r[3] or "", "vehicle_type": r[4] or "",
            "vehicle_no": r[5] or "",
            "inspection_date": insp, "expiry_date": str(r[7]),
            "entered_by": r[8] or "",
        })

    return jsonify({
        "ok": True,
        "data": data,
        "total": len(rows),
        "filtered": len(data),
        "can_delete": session.get("role") == "admin"
    })


@app.route("/api/export.xlsx", methods=["GET"])
@login_required()
def api_export_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Inspections"
    ws.append(HEADERS)
    for idx, row in enumerate(get_all_inspections(), start=1):
        ws.append([
            idx, row[1], row[2], row[3] or "", row[4] or "", row[5] or "",
            str(row[6]), str(row[7]), row[8] or ""
        ])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="inspections.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/update", methods=["POST"])
@login_required()
def api_update():
    d = request.get_json() or {}
    try:
        update_inspection(
            int(d["id"]), d["name"], d["phone"], d.get("email", ""),
            d.get("vehicle_type", ""), d.get("vehicle_no", ""),
            d["inspection_date"], d["expiry_date"]
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400


@app.route("/api/delete", methods=["POST"])
@login_required(role="admin")
def api_delete():
    d = request.get_json() or {}
    try:
        delete_inspection(int(d["id"]))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400


# ================= MONTHLY CHART =================
@app.route("/api/monthly-summary", methods=["GET"])
@login_required(role="admin")
def api_monthly_summary():
    year = request.args.get("year")
    year = int(year) if year else None
    data = get_monthly_counts(year)
    return jsonify({"ok": True, "data": data})


# ================= MANUAL TRIGGERS =================
@app.route("/api/send-daily-mail-now", methods=["POST"])
@login_required(role="admin")
def api_send_daily_now():
    try:
        send_daily_email()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/api/send-monthly-mail-now", methods=["POST"])
@login_required(role="admin")
def api_send_monthly_now():
    d = request.get_json() or {}
    today = app_today()
    year = int(d.get("year") or today.year)
    month = int(d.get("month") or today.month)
    try:
        send_monthly_email(year, month)
        return jsonify({"ok": True, "year": year, "month": month})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


# ================= MAIN =================
init_db()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("APP_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )