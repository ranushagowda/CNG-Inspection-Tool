import argparse
import os
import sqlite3

import psycopg
from werkzeug.security import generate_password_hash

from storage import init_db


def _select_columns(cursor, table, desired):
    cursor.execute(f"PRAGMA table_info({table});")
    available = {row[1] for row in cursor.fetchall()}
    return ", ".join(
        column if column in available else "NULL AS " + column
        for column in desired
    )


def migrate(source_path):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Set DATABASE_URL to the destination PostgreSQL URL")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    init_db(allow_empty=True, seed_initial_admin=True)
    source = sqlite3.connect(source_path)
    target = psycopg.connect(database_url)
    source.row_factory = sqlite3.Row

    try:
        src = source.cursor()
        src.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in src.fetchall()}
        if not {"users", "inspections"}.issubset(tables):
            raise RuntimeError("Source file is missing the users or inspections table")

        user_columns = (
            "id", "username", "password", "role", "full_name", "phone",
            "email", "created_at",
        )
        inspection_columns = (
            "id", "name", "phone", "email", "vehicle_type", "vehicle_no",
            "inspection_date", "expiry_date", "entered_by", "created_at",
        )
        src.execute("SELECT " + _select_columns(src, "users", user_columns) +
                    " FROM users ORDER BY id;")
        users = src.fetchall()
        src.execute("SELECT " + _select_columns(src, "inspections", inspection_columns) +
                    " FROM inspections ORDER BY id;")
        inspections = src.fetchall()

        with target.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inspections;")
            if cur.fetchone()[0]:
                raise RuntimeError("Destination database already contains inspection data")
            cur.execute("SELECT id, username, role FROM users ORDER BY id;")
            existing_users = cur.fetchall()
            bootstrap_username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
            if existing_users:
                if (len(existing_users) != 1
                        or existing_users[0][1] != bootstrap_username
                        or existing_users[0][2] != "admin"):
                    raise RuntimeError(
                        "Destination has users other than the configured bootstrap "
                        "admin; refusing to overwrite it"
                    )
                cur.execute("DELETE FROM users WHERE id=%s;", (existing_users[0][0],))

            for row in users:
                password = row["password"] or ""
                if (row["username"] == bootstrap_username
                        and os.environ.get("INITIAL_ADMIN_PASSWORD")):
                    password = os.environ["INITIAL_ADMIN_PASSWORD"]
                if not password.startswith(("scrypt:", "pbkdf2:")):
                    password = generate_password_hash(password)
                cur.execute("""
                    INSERT INTO users
                        (id, username, password, role, full_name, phone, email, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    row["id"], row["username"], password, row["role"],
                    row["full_name"], row["phone"], row["email"], row["created_at"],
                ))

            for row in inspections:
                cur.execute("""
                    INSERT INTO inspections
                        (id, name, phone, email, vehicle_type, vehicle_no,
                         inspection_date, expiry_date, entered_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, tuple(row[column] for column in inspection_columns))

            for table in ("users", "inspections"):
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), "
                    f"EXISTS(SELECT 1 FROM {table}));"
                )
        target.commit()
        print(
            f"Migrated {len(users)} user accounts and "
            f"{len(inspections)} inspection records."
        )
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copy the local CNG SQLite database to PostgreSQL."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "cng.db"),
        help="Path to the existing cng.db file (default: ./cng.db)",
    )
    migrate(parser.parse_args().source)
