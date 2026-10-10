import os
import hmac
import sqlite3
from datetime import date

import psycopg
from werkzeug.security import check_password_hash, generate_password_hash


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cng.db")


def _is_postgres():
    return bool(os.environ.get("DATABASE_URL"))


def _connect():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        return psycopg.connect(database_url)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _execute(cursor, sql, params=()):
    if _is_postgres():
        sql = sql.replace("?", "%s")
    return cursor.execute(sql, params)


def _hash_password(password):
    return generate_password_hash(password)


def init_db(allow_empty=False, seed_initial_admin=True):
    conn = _connect()
    cur = conn.cursor()
    try:
        if _is_postgres():
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    full_name TEXT,
                    phone TEXT,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inspections (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT,
                    vehicle_type TEXT,
                    vehicle_no TEXT,
                    inspection_date TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    entered_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            migrations = (
                ("inspections", "vehicle_type"),
                ("inspections", "vehicle_no"),
                ("inspections", "entered_by"),
                ("users", "full_name"),
                ("users", "phone"),
                ("users", "email"),
            )
            for table, column in migrations:
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} TEXT;"
                )
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    full_name TEXT,
                    phone TEXT,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT,
                    vehicle_type TEXT,
                    vehicle_no TEXT,
                    inspection_date TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    entered_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            for table, column in (
                ("inspections", "vehicle_type"),
                ("inspections", "vehicle_no"),
                ("inspections", "entered_by"),
                ("users", "full_name"),
                ("users", "phone"),
                ("users", "email"),
            ):
                cur.execute(f"PRAGMA table_info({table});")
                existing = {row[1] for row in cur.fetchall()}
                if column not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT;")

        _execute(cur, "SELECT COUNT(*) FROM users WHERE role='admin';")
        has_admin = cur.fetchone()[0] > 0
        if not has_admin and seed_initial_admin:
            username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
            password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
            if username and password:
                if len(password) < 12:
                    raise RuntimeError(
                        "INITIAL_ADMIN_PASSWORD must be at least 12 characters"
                    )
                _execute(
                    cur,
                    "INSERT INTO users (username, password, role) "
                    "VALUES (?, ?, 'admin') ON CONFLICT(username) DO NOTHING;",
                    (username, _hash_password(password)),
                )
                _execute(cur, "SELECT COUNT(*) FROM users WHERE role='admin';")
                has_admin = cur.fetchone()[0] > 0

        if not has_admin and not allow_empty:
            raise RuntimeError(
                "No admin account exists. Set INITIAL_ADMIN_USERNAME and "
                "INITIAL_ADMIN_PASSWORD, or migrate your existing database."
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def get_users():
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, "SELECT id, username, role FROM users ORDER BY id ASC;")
        return [tuple(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def get_user_profile(user_id):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(
            cur,
            "SELECT id, username, role, full_name, phone, email "
            "FROM users WHERE id=?;",
            (user_id,),
        )
        row = cur.fetchone()
        return tuple(row) if row else None
    finally:
        cur.close()
        conn.close()


def update_user_profile(user_id, full_name, phone, email):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(
            cur,
            "UPDATE users SET full_name=?, phone=?, email=? WHERE id=?;",
            (full_name, phone, email, user_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def add_user(username, password, role="user"):
    if len(password) < 12:
        return None, "Password must be at least 12 characters"
    conn = _connect()
    cur = conn.cursor()
    try:
        if _is_postgres():
            _execute(
                cur,
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?) "
                "RETURNING id;",
                (username, _hash_password(password), role),
            )
            new_id = cur.fetchone()[0]
        else:
            _execute(
                cur,
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?);",
                (username, _hash_password(password), role),
            )
            new_id = cur.lastrowid
        conn.commit()
        return new_id, None
    except (sqlite3.IntegrityError, psycopg.IntegrityError):
        conn.rollback()
        return None, "Username already exists"
    finally:
        cur.close()
        conn.close()


def update_user(uid, username=None, password=None, role=None):
    if role and role not in ("admin", "user"):
        return False, "Invalid role"
    if password and len(password) < 12:
        return False, "Password must be at least 12 characters"
    conn = _connect()
    cur = conn.cursor()
    try:
        if role:
            _execute(cur, "SELECT role FROM users WHERE id=?;", (uid,))
            current = cur.fetchone()
            if not current:
                return False, "User not found"
            if current[0] == "admin" and role != "admin":
                _execute(cur, "SELECT COUNT(*) FROM users WHERE role='admin';")
                if cur.fetchone()[0] <= 1:
                    return False, "Cannot demote the only admin"

        fields, values = [], []
        if username:
            fields.append("username=?")
            values.append(username)
        if password:
            fields.append("password=?")
            values.append(_hash_password(password))
        if role:
            fields.append("role=?")
            values.append(role)

        if not fields:
            return True, None

        values.append(uid)
        _execute(
            cur,
            f"UPDATE users SET {', '.join(fields)} WHERE id=?;",
            values,
        )
        conn.commit()
        return True, None
    except (sqlite3.IntegrityError, psycopg.IntegrityError):
        conn.rollback()
        return False, "Username already exists"
    finally:
        cur.close()
        conn.close()


def delete_user(uid):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, "SELECT role FROM users WHERE id=?;", (uid,))
        row = cur.fetchone()
        if not row:
            return False, "User not found"
        if row[0] == "admin":
            _execute(cur, "SELECT COUNT(*) FROM users WHERE role='admin';")
            if cur.fetchone()[0] <= 1:
                return False, "Cannot delete the only admin"
        _execute(cur, "DELETE FROM users WHERE id=?;", (uid,))
        conn.commit()
        return True, None
    finally:
        cur.close()
        conn.close()


def verify_login(username, password):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(
            cur,
            "SELECT id, username, role, password FROM users WHERE username=?;",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return None

        stored = row[3]
        if stored.startswith(("scrypt:", "pbkdf2:")):
            valid = check_password_hash(stored, password)
        else:
            valid = hmac.compare_digest(stored, password)
            if valid:
                _execute(
                    cur,
                    "UPDATE users SET password=? WHERE id=?;",
                    (_hash_password(password), row[0]),
                )
                conn.commit()
        return tuple(row[:3]) if valid else None
    finally:
        cur.close()
        conn.close()


def insert_inspection(name, phone, email, vehicle_type, vehicle_no,
                      inspection_date, expiry_date, entered_by):
    conn = _connect()
    cur = conn.cursor()
    try:
        query = """
            INSERT INTO inspections
                (name, phone, email, vehicle_type, vehicle_no,
                 inspection_date, expiry_date, entered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (name, phone, email, vehicle_type, vehicle_no,
                  inspection_date, expiry_date, entered_by)
        if _is_postgres():
            _execute(cur, query + " RETURNING id;", values)
            new_id = cur.fetchone()[0]
        else:
            _execute(cur, query, values)
            new_id = cur.lastrowid
        conn.commit()
        return new_id
    finally:
        cur.close()
        conn.close()


def get_all_inspections():
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, """
            SELECT id, name, phone, email, vehicle_type, vehicle_no,
                   inspection_date, expiry_date, entered_by, created_at
            FROM inspections ORDER BY id ASC;
        """)
        raw = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    rows = []
    for row in raw:
        values = list(row)
        for index in (6, 7):
            try:
                values[index] = date.fromisoformat(str(values[index]))
            except (TypeError, ValueError):
                pass
        rows.append(tuple(values))
    return rows


def update_inspection(rid, name, phone, email, vehicle_type, vehicle_no,
                      inspection_date, expiry_date):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, """
            UPDATE inspections
            SET name=?, phone=?, email=?, vehicle_type=?, vehicle_no=?,
                inspection_date=?, expiry_date=?
            WHERE id=?;
        """, (name, phone, email, vehicle_type, vehicle_no,
              inspection_date, expiry_date, rid))
        if cur.rowcount == 0:
            raise ValueError("Inspection record not found")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def delete_inspection(rid):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, "DELETE FROM inspections WHERE id=?;", (rid,))
        if cur.rowcount == 0:
            raise ValueError("Inspection record not found")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_user_entry_counts(from_date=None, to_date=None):
    conn = _connect()
    cur = conn.cursor()
    try:
        sql = """
            SELECT u.username, COUNT(i.id) AS cnt
            FROM users u
            LEFT JOIN inspections i ON i.entered_by = u.username
        """
        where, params = [], []
        if from_date:
            where.append("i.inspection_date >= ?")
            params.append(from_date)
        if to_date:
            where.append("i.inspection_date <= ?")
            params.append(to_date)
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " GROUP BY u.username ORDER BY cnt DESC, u.username ASC;"
        _execute(cur, sql, params)
        return [{"username": row[0], "count": row[1]} for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def get_today_entries_summary(day_str):
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, """
            SELECT entered_by, COUNT(*)
            FROM inspections WHERE inspection_date=?
            GROUP BY entered_by ORDER BY entered_by;
        """, (day_str,))
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        cur.close()
        conn.close()


def get_admin_emails():
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, """
            SELECT username, email FROM users
            WHERE role='admin' AND email IS NOT NULL AND email <> ''
            ORDER BY id;
        """)
        return [(row[0], row[1]) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def get_monthly_counts(year=None):
    if year is None:
        year = date.today().year
    conn = _connect()
    cur = conn.cursor()
    try:
        _execute(cur, """
            SELECT CAST(SUBSTR(inspection_date, 6, 2) AS INTEGER) AS month,
                   COUNT(*) AS cnt
            FROM inspections
            WHERE CAST(SUBSTR(inspection_date, 1, 4) AS INTEGER)=?
            GROUP BY month ORDER BY month;
        """, (year,))
        counts = {month: 0 for month in range(1, 13)}
        for month, count in cur.fetchall():
            counts[month] = count
        return [{"month": month, "count": counts[month]} for month in range(1, 13)]
    finally:
        cur.close()
        conn.close()
