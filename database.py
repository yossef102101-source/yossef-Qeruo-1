import os
import sqlite3
import secrets
import time
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "qureo_platform.db"))

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # جدول المستخدمين والصلاحيات والحدود المسموح بها
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        session_token TEXT UNIQUE NOT NULL,
        can_solve INTEGER DEFAULT 0,
        max_accounts INTEGER DEFAULT 0,
        used_accounts INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        last_login TEXT NOT NULL
    )
    """)

    # جدول الحسابات/الطلبات المرسلة للحل (مرتبطة بصاحب الحساب)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS solve_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_phone TEXT NOT NULL,
        student_code TEXT NOT NULL,
        school_type TEXT NOT NULL,
        grade TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT DEFAULT 'in_queue',
        queue_position INTEGER DEFAULT 1,
        progress INTEGER DEFAULT 0,
        logs_json TEXT DEFAULT '[]',
        error_msg TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(owner_phone) REFERENCES users(phone)
    )
    """)

    # جدول سجل التغييرات والصلاحيات الإدارية (Audit Log)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        target_phone TEXT,
        target_name TEXT,
        details TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # جدول إعدادات الأداة العامة
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    # القيم الافتراضية للإعدادات
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('is_open', '1')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance_message', 'عذراً، الأداة مغلقة مؤقتاً لتحديث الخادم وتخفيف الضغط. يرجى المحاولة لاحقاً.')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_can_solve', '0')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_max_accounts', '0')")

    conn.commit()
    conn.close()

def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def log_audit(action_type: str, details: str, target_phone: str = "-", target_name: str = "-"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_logs (action_type, target_phone, target_name, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (action_type, target_phone, target_name, details, now_str())
    )
    conn.commit()
    conn.close()

def register_or_login_user(full_name: str, phone: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    if existing:
        # تحديث الاسم وآخر دخول دون المساس بالصلاحيات أو الرصيد
        new_token = existing["session_token"] or secrets.token_urlsafe(32)
        cur.execute(
            "UPDATE users SET full_name = ?, last_login = ?, session_token = ? WHERE phone = ?",
            (full_name, now_str(), new_token, phone)
        )
        conn.commit()
        user_row = cur.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        conn.close()
        return dict(user_row)

    # مستخدم جديد: تسجيل مفتوح للجميع، الصلاحية الافتراضية مغلقة (can_solve = 0)
    default_solve = int(get_setting("default_can_solve", "0"))
    default_quota = int(get_setting("default_max_accounts", "0"))
    token = secrets.token_urlsafe(32)
    now = now_str()

    cur.execute(
        """INSERT INTO users (full_name, phone, session_token, can_solve, max_accounts, used_accounts, created_at, last_login)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
        (full_name, phone, token, default_solve, default_quota, now, now)
    )
    conn.commit()
    user_row = cur.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    log_audit("USER_REGISTER", f"تسجيل مستخدم جديد: {full_name}", phone, full_name)
    return dict(user_row)

def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE session_token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_phone(phone: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_permissions(phone: str, can_solve: int, max_accounts: int):
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if not user:
        conn.close()
        return False
    conn.execute(
        "UPDATE users SET can_solve = ?, max_accounts = ? WHERE phone = ?",
        (1 if can_solve else 0, max(0, int(max_accounts)), phone)
    )
    conn.commit()
    conn.close()
    status_txt = "مفعّلة 🟢" if can_solve else "موقوفة 🔴"
    log_audit(
        "PERMISSION_UPDATE",
        f"تحديث الصلاحية إلى ({status_txt}) والحد المسموح إلى ({max_accounts} حسابات)",
        phone,
        user["full_name"]
    )
    return True

def increment_used_accounts(phone: str):
    conn = get_conn()
    conn.execute("UPDATE users SET used_accounts = used_accounts + 1 WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()

def get_all_users() -> List[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT id, full_name, phone, can_solve, max_accounts, used_accounts, created_at, last_login FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_audit_logs(limit: int = 100) -> List[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
