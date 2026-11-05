"""Database layer for the Smart AI Surveillance System.

Uses SQLite (stdlib) so it runs anywhere with zero native dependencies.
Creates the schema and seeds demo data (cameras, alerts, incidents,
users with RBAC roles, AI settings) on first run.
"""
import os
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surveillance.db")


def get_conn():
    """Return a connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('Security','Admin','Management')),
    title         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cameras (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    zone       TEXT NOT NULL,
    resolution TEXT NOT NULL DEFAULT '1080p',
    ai_module  INTEGER NOT NULL DEFAULT 1,
    status     TEXT NOT NULL DEFAULT 'Online',
    image_url  TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_code   TEXT UNIQUE NOT NULL,
    camera_id    INTEGER NOT NULL REFERENCES cameras(id),
    anomaly_type TEXT NOT NULL,
    severity     TEXT NOT NULL CHECK (severity IN ('critical','warning','info')),
    confidence   INTEGER NOT NULL,
    evidence_path TEXT,
    incident_code TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','dismissed','resolved')),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_code   TEXT UNIQUE NOT NULL,
    incident_type   TEXT NOT NULL,
    assigned_officer TEXT,
    status          TEXT NOT NULL DEFAULT 'Open'
                    CHECK (status IN ('Open','Dispatched','In Progress','Resolved')),
    camera_ref      TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _seed(conn):
    now = datetime.now()

    def ts(mins_ago=0):
        return (now - timedelta(minutes=mins_ago)).strftime("%Y-%m-%d %H:%M:%S")

    # --- Users (RBAC) ---
    users = [
        ("kamogelo", "Security@123", "Officer Kamogelo", "Security", "Security Specialist"),
        ("mokgadi", "Admin@123", "Mokgadi", "Admin", "System Administrator"),
        ("george", "Manage@123", "George", "Management", "Campus Executive"),
    ]
    for uname, pwd, name, role, title in users:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, title) "
            "VALUES (?,?,?,?,?)",
            (uname, generate_password_hash(pwd), name, role, title),
        )

    # --- Cameras ---
    U = "https://images.unsplash.com/"
    cams = [
        ("CAM-01", "Main Entrance Gate", "North Gate", "1080p", 1, "Online",
         U + "photo-1577495508048-b635879837f1?auto=format&fit=crop&w=600&q=80"),
        ("CAM-02", "Library Quadrangle", "Central Quad", "4K", 1, "Online",
         U + "photo-1541829070764-84a7d30dd3f3?auto=format&fit=crop&w=600&q=80"),
        ("CAM-03", "Science Complex Alley", "East Wing", "1080p", 1, "Online",
         U + "photo-1526778548025-fa2f459cd5c1?auto=format&fit=crop&w=600&q=80"),
        ("CAM-04", "Student Parking West", "West Lot", "1080p", 1, "Online",
         U + "photo-1562774053-701939374585?auto=format&fit=crop&w=600&q=80"),
    ]
    for c in cams:
        conn.execute(
            "INSERT INTO cameras (code,name,zone,resolution,ai_module,status,image_url) "
            "VALUES (?,?,?,?,?,?,?)", c)

    # --- Alerts ---
    alerts = [
        ("ALT-9042", 1, "Unintended Access Breach", "critical", 89, "active", ts(2)),
        ("ALT-9041", 3, "Suspicious Loitering", "warning", 92, "active", ts(7)),
        ("ALT-9038", 2, "Crowd Overcrowding", "info", 78, "resolved", ts(60)),
    ]
    for a in alerts:
        conn.execute(
            "INSERT INTO alerts (alert_code,camera_id,anomaly_type,severity,confidence,status,created_at) "
            "VALUES (?,?,?,?,?,?,?)", a)

    # --- Incidents ---
    incidents = [
        ("INC-2026-001", "Perimeter Fence Intrusion", "Officer William",
         "In Progress", "CAM-01", "Auto-logged from ALT-9042", ts(4)),
        ("INC-2026-000", "Unattended Bag Detection", "Officer Boikanyo",
         "Resolved", "CAM-02", "Cleared by security team", ts(60 * 24)),
    ]
    for i in incidents:
        conn.execute(
            "INSERT INTO incidents (incident_code,incident_type,assigned_officer,status,camera_ref,notes,created_at) "
            "VALUES (?,?,?,?,?,?,?)", i)

    # --- Settings ---
    for k, v in [("confidence_cutoff", "80"), ("loitering_seconds", "45"),
                 ("ai_model", "YOLOv8-Anomaly")]:
        conn.execute("INSERT INTO settings (key,value) VALUES (?,?)", (k, v))

    conn.commit()


def init_db(force=False):
    """Create schema and seed demo data. Set force=True to rebuild."""
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Safe migration for databases created by earlier FullStack versions.
    alert_columns = {row[1] for row in conn.execute("PRAGMA table_info(alerts)")}
    if "evidence_path" not in alert_columns:
        conn.execute("ALTER TABLE alerts ADD COLUMN evidence_path TEXT")
    if "incident_code" not in alert_columns:
        conn.execute("ALTER TABLE alerts ADD COLUMN incident_code TEXT")
    conn.commit()
    if fresh:
        _seed(conn)
    conn.close()


if __name__ == "__main__":
    init_db(force=True)
    print("Database initialised at", DB_PATH)
