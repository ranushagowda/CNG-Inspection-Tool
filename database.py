import storage as _storage
from storage import (
    add_user,
    delete_inspection,
    delete_user,
    get_admin_emails,
    get_all_inspections,
    get_monthly_counts,
    get_today_entries_summary,
    get_user_entry_counts,
    get_user_profile,
    get_users,
    init_db,
    insert_inspection,
    update_inspection,
    update_user,
    update_user_profile,
    verify_login,
)

__all__ = [
    "add_user",
    "delete_inspection",
    "delete_user",
    "get_admin_emails",
    "get_all_inspections",
    "get_monthly_counts",
    "get_today_entries_summary",
    "get_user_entry_counts",
    "get_user_profile",
    "get_users",
    "init_db",
    "insert_inspection",
    "set_db_path",
    "update_inspection",
    "update_user",
    "update_user_profile",
    "verify_login",
]


def set_db_path(path):
    _storage.DB_PATH = path
