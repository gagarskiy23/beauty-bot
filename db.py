import sqlite3
from datetime import datetime, date, time
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            name TEXT,
            phone TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER REFERENCES masters(id),
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration_min INTEGER DEFAULT 60
        );

        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER REFERENCES masters(id),
            day_of_week INTEGER, -- 0=mon, 6=sun
            start_time TEXT,
            end_time TEXT
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER REFERENCES masters(id),
            client_name TEXT NOT NULL,
            client_phone TEXT,
            service_id INTEGER REFERENCES services(id),
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            confirmed INTEGER DEFAULT 0,
            cancelled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS master_settings (
            master_id INTEGER PRIMARY KEY,
            notify_before_min INTEGER DEFAULT 120,
            auto_confirm INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER UNIQUE REFERENCES masters(id),
            stars_subscription_id TEXT,
            expires_at TEXT,
            active INTEGER DEFAULT 0,
            auto_renew INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

# ---------- Masters ----------
def register_master(tg_id, name, phone):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO masters (tg_id, name, phone) VALUES (?, ?, ?)", (tg_id, name, phone))
    cur.execute("INSERT OR IGNORE INTO master_settings (master_id) VALUES (?)", (cur.lastrowid or tg_id,))
    conn.commit()
    conn.close()

def get_master(tg_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM masters WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

# ---------- Services ----------
def add_service(master_id, name, price, duration=60):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO services (master_id, name, price, duration_min) VALUES (?, ?, ?, ?)",
                (master_id, name, price, duration))
    conn.commit()
    conn.close()

def get_services(master_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE master_id = ?", (master_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_service(service_id, name, price, duration=60):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE services SET name=?, price=?, duration_min=? WHERE id=?",
                (name, price, duration, service_id))
    conn.commit()
    conn.close()

def delete_service(service_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()

# ---------- Appointments ----------
def book_appointment(master_id, client_name, client_phone, service_id, date, time_slot):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""INSERT INTO appointments (master_id, client_name, client_phone, service_id, date, time)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (master_id, client_name, client_phone, service_id, date, time_slot))
    conn.commit()
    conn.close()

def get_appointments(master_id, limit=20):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT a.*, s.name as service_name, s.price
                   FROM appointments a
                   LEFT JOIN services s ON a.service_id = s.id
                   WHERE a.master_id = ? AND a.cancelled = 0
                   ORDER BY a.date DESC, a.time DESC
                   LIMIT ?""", (master_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_today_appointments(master_id):
    today = date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT a.*, s.name as service_name, s.price
                   FROM appointments a
                   LEFT JOIN services s ON a.service_id = s.id
                   WHERE a.master_id = ? AND a.date = ? AND a.cancelled = 0
                   ORDER BY a.time""", (master_id, today))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_upcoming_appointments(master_id, limit=5):
    today = date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT a.*, s.name as service_name, s.price
                   FROM appointments a
                   LEFT JOIN services s ON a.service_id = s.id
                   WHERE a.master_id = ? AND a.date >= ? AND a.cancelled = 0
                   ORDER BY a.date, a.time
                   LIMIT ?""", (master_id, today, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def confirm_appointment(app_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE appointments SET confirmed = 1 WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

def cancel_appointment(app_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE appointments SET cancelled = 1 WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

# ---------- Subscriptions ----------
def activate_subscription(master_id, duration_days=30):
    from datetime import datetime, timedelta
    expires = (datetime.now() + timedelta(days=duration_days)).isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscriptions (master_id, expires_at, active)
        VALUES (?, ?, 1)
        ON CONFLICT(master_id) DO UPDATE SET
            expires_at = excluded.expires_at,
            active = 1
    """, (master_id, expires))
    conn.commit()
    conn.close()

def check_subscription(master_id):
    from datetime import datetime
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscriptions WHERE master_id = ?", (master_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return False

    sub = dict(row)
    if not sub["active"]:
        return False

    expires = datetime.fromisoformat(sub["expires_at"])
    if expires < datetime.now():
        return False

    return True

def get_subscription(master_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscriptions WHERE master_id = ?", (master_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
