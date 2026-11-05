"""Smart AI Surveillance System - Flask backend.

Serves the dashboard UI and a REST API backed by SQLite. Implements
session-based authentication and role-based access control (RBAC) for
three roles: Security, Admin, Management.

Run:
    pip install -r requirements.txt
    python database.py      # build + seed the DB (optional; auto on start)
    python app.py           # serves on http://127.0.0.1:5000
"""
import functools
import hmac
import os
import re
import uuid
import threading
from pathlib import Path
from datetime import datetime

from flask import (Flask, g, jsonify, request, session,
                   send_from_directory, abort)
from werkzeug.security import check_password_hash

import database

app = Flask(__name__, static_folder="static")
# In production load this from an environment variable / secret manager.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
database.init_db()

# Browser webcam inference is loaded only when the first frame arrives.
WEB_CAMERA_MODEL_PATH = Path(__file__).resolve().parent.parent / "ai_detection" / "yolov8n.pt"
_webcam_model = None
_webcam_model_lock = threading.Lock()
_webcam_inference_lock = threading.Lock()
_webcam_alert_cooldowns = {}


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------
@app.before_request
def _open_db():
    g.db = database.get_conn()


@app.teardown_request
def _close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    row = g.db.execute(
        "SELECT id, username, full_name, role, title FROM users WHERE id=?",
        (uid,)).fetchone()
    return dict(row) if row else None


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return jsonify(error="Authentication required"), 401
        return fn(*a, **kw)
    return wrapper


def roles_required(*roles):
    """Restrict an endpoint to the given roles (RBAC enforcement)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                return jsonify(error="Authentication required"), 401
            if user["role"] not in roles:
                return jsonify(error="Forbidden: insufficient role"), 403
            return fn(*a, **kw)
        return wrapper
    return deco


# --------------------------------------------------------------------------
# Static UI
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/login")
def login_page():
    return send_from_directory("static", "login.html")


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    row = g.db.execute("SELECT * FROM users WHERE username=?",
                       (data.get("username", "").strip(),)).fetchone()
    if row and check_password_hash(row["password_hash"], data.get("password", "")):
        session["uid"] = row["id"]
        return jsonify(user={"full_name": row["full_name"],
                             "role": row["role"], "title": row["title"]})
    return jsonify(error="Invalid username or password"), 401


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required
def me():
    return jsonify(user=current_user())


# --------------------------------------------------------------------------
# Dashboard metrics
# --------------------------------------------------------------------------
@app.get("/api/dashboard/stats")
@login_required
def dashboard_stats():
    db = g.db
    cams = db.execute("SELECT COUNT(*) c FROM cameras").fetchone()["c"]
    online = db.execute("SELECT COUNT(*) c FROM cameras WHERE status='Online'").fetchone()["c"]
    active = db.execute("SELECT COUNT(*) c FROM alerts WHERE status='active'").fetchone()["c"]
    today = datetime.now().strftime("%Y-%m-%d")
    inc_today = db.execute(
        "SELECT COUNT(*) c FROM incidents WHERE substr(created_at,1,10)=?",
        (today,)).fetchone()["c"]
    resolved = db.execute(
        "SELECT COUNT(*) c FROM incidents WHERE status='Resolved'").fetchone()["c"]
    avg_conf = db.execute(
        "SELECT AVG(confidence) a FROM alerts").fetchone()["a"] or 0
    return jsonify(
        connected_feeds=cams, online_feeds=online,
        active_anomalies=active, incidents_today=inc_today,
        incidents_resolved=resolved, avg_confidence=round(avg_conf, 1))


# --------------------------------------------------------------------------
# Cameras
# --------------------------------------------------------------------------
@app.get("/api/cameras")
@login_required
def list_cameras():
    rows = g.db.execute("SELECT * FROM cameras ORDER BY code").fetchall()
    return jsonify(cameras=[dict(r) for r in rows])


@app.get("/api/camera/status")
@login_required
def webcam_ai_status():
    """Report whether browser webcam inference can run on this server."""
    import importlib.util
    missing = [name for name in ("cv2", "numpy", "ultralytics")
               if importlib.util.find_spec(name) is None]
    model_exists = WEB_CAMERA_MODEL_PATH.is_file()
    ready = not missing and model_exists
    return jsonify(
        ready=ready,
        model_loaded=_webcam_model is not None,
        model_file=WEB_CAMERA_MODEL_PATH.name,
        model_exists=model_exists,
        missing_dependencies=missing,
        supported_classes=["person", "knife"],
        unsupported_classes=["smoke", "fire", "fall", "violence", "other weapons"],
        message=("AI model is available. Start the webcam to begin analysis."
                 if ready else "AI inference is unavailable. Install requirements and check the model file."))


@app.post("/api/cameras")
@roles_required("Admin")
def add_camera():
    d = request.get_json(silent=True) or {}
    required = ("code", "name", "zone")
    if not all(d.get(k) for k in required):
        return jsonify(error="code, name and zone are required"), 400
    try:
        cur = g.db.execute(
            "INSERT INTO cameras (code,name,zone,resolution,ai_module,status,image_url) "
            "VALUES (?,?,?,?,?,?,?)",
            (d["code"], d["name"], d["zone"], d.get("resolution", "1080p"),
             1 if d.get("ai_module", True) else 0, "Online", d.get("image_url")))
        g.db.commit()
    except Exception as e:  # e.g. duplicate code
        return jsonify(error=str(e)), 400
    return jsonify(id=cur.lastrowid), 201


@app.delete("/api/cameras/<int:cam_id>")
@roles_required("Admin")
def delete_camera(cam_id):
    g.db.execute("DELETE FROM cameras WHERE id=?", (cam_id,))
    g.db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
@app.get("/api/alerts")
@login_required
def list_alerts():
    rows = g.db.execute(
        "SELECT a.*, c.code cam_code, c.name cam_name "
        "FROM alerts a JOIN cameras c ON c.id=a.camera_id "
        "ORDER BY a.created_at DESC").fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["evidence_url"] = ("/evidence/" + Path(item["evidence_path"]).name
                                if item.get("evidence_path") else None)
        items.append(item)
    return jsonify(alerts=items)


@app.post("/api/alerts/<int:alert_id>/dismiss")
@roles_required("Security", "Admin")
def dismiss_alert(alert_id):
    g.db.execute("UPDATE alerts SET status='dismissed' WHERE id=?", (alert_id,))
    g.db.commit()
    return jsonify(ok=True)



# --------------------------------------------------------------------------
# AI ingestion and evidence
# --------------------------------------------------------------------------
def _ai_token_valid():
    expected = os.environ.get("AI_INGEST_TOKEN", "")
    supplied = request.headers.get("X-AI-Token", "")
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _next_alert_code(db):
    row = db.execute(
        "SELECT MAX(CAST(substr(alert_code,5) AS INTEGER)) AS mx "
        "FROM alerts WHERE alert_code LIKE 'ALT-%'").fetchone()
    seq = (row["mx"] + 1) if row and row["mx"] is not None else 1
    return f"ALT-{seq:06d}"


@app.post("/api/ai/alerts")
def ingest_ai_alert():
    """Receive a detection from the local YOLO process (shared-secret auth)."""
    if not _ai_token_valid():
        return jsonify(error="AI ingestion is not configured or token is invalid"), 401

    camera_code = (request.form.get("camera") or "CAM-01").strip()
    event = (request.form.get("event") or "UNKNOWN ANOMALY").strip().upper()
    try:
        confidence = float(request.form.get("confidence", "0"))
    except (TypeError, ValueError):
        return jsonify(error="confidence must be numeric"), 400
    confidence = max(0.0, min(100.0, confidence))
    camera = g.db.execute("SELECT id, code FROM cameras WHERE code=?", (camera_code,)).fetchone()
    if not camera:
        return jsonify(error=f"Unknown camera code: {camera_code}"), 404

    severity = "critical" if event in {"TRESPASSING", "DANGEROUS OBJECT", "WEAPON DETECTED"} else "warning"
    file = request.files.get("evidence")
    evidence_name = None
    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            return jsonify(error="Evidence must be JPG or PNG"), 400
        evidence_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}{ext}"
        file.save(EVIDENCE_DIR / evidence_name)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    code = _next_alert_code(g.db)
    cur = g.db.execute(
        "INSERT INTO alerts (alert_code,camera_id,anomaly_type,severity,confidence,evidence_path,status,created_at) "
        "VALUES (?,?,?,?,?,?, 'active',?)",
        (code, camera["id"], event.replace("_", " "), severity,
         int(round(confidence)), evidence_name, now))
    alert_id = cur.lastrowid

    # Automatically open an incident linked to the same camera and detection.
    incident_code = _next_incident_code(g.db)
    notes = f"Automatically created from AI alert {code}. Confidence: {confidence:.1f}%."
    if evidence_name:
        notes += f" Evidence: {evidence_name}."
    g.db.execute(
        "INSERT INTO incidents (incident_code,incident_type,assigned_officer,status,camera_ref,notes,created_at) "
        "VALUES (?,?,NULL,'Open',?,?,?)",
        (incident_code, event.replace("_", " "), camera["code"], notes, now))
    g.db.execute("UPDATE alerts SET incident_code=? WHERE id=?", (incident_code, alert_id))
    g.db.commit()
    return jsonify(ok=True, alert_id=alert_id, alert_code=code,
                   incident_code=incident_code, evidence_url=(f"/evidence/{evidence_name}" if evidence_name else None)), 201


@app.post("/api/camera/analyze")
@login_required
def analyze_webcam_frame():
    """Analyse one browser-captured webcam frame and return object boxes.

    The bundled COCO YOLOv8 model currently supports person and knife classes.
    Smoke/fire/fall detection requires separately trained models and is not
    claimed by this endpoint.
    """
    global _webcam_model
    frame_file = request.files.get("frame")
    camera_code = (request.form.get("camera_code") or "CAM-01").strip()
    if not frame_file:
        return jsonify(error="A webcam frame is required"), 400
    camera = g.db.execute("SELECT id, code FROM cameras WHERE code=?", (camera_code,)).fetchone()
    if not camera:
        return jsonify(error=f"Unknown camera code: {camera_code}"), 404

    raw = frame_file.read()
    if not raw or len(raw) > 3 * 1024 * 1024:
        return jsonify(error="Frame is empty or exceeds the 3 MB limit"), 400

    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        return jsonify(error=f"AI dependencies are missing: {exc}. Install surveillance/requirements.txt."), 503

    if _webcam_model is None:
        with _webcam_model_lock:
            if _webcam_model is None:
                if not WEB_CAMERA_MODEL_PATH.exists():
                    return jsonify(error=f"YOLO model file not found: {WEB_CAMERA_MODEL_PATH}"), 503
                _webcam_model = YOLO(str(WEB_CAMERA_MODEL_PATH))

    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return jsonify(error="Could not decode webcam image"), 400

    height, width = image.shape[:2]
    # Same calibrated rectangle as the existing 640x480 detector, scaled to frame size.
    zx1, zy1 = int(width * 450 / 640), int(height * 50 / 480)
    zx2, zy2 = int(width * 630 / 640), int(height * 430 / 480)
    with _webcam_inference_lock:
        result = _webcam_model.predict(image, classes=[0, 43], conf=0.35, verbose=False)[0]
    detections = []
    now_epoch = datetime.now().timestamp()
    alert_events = []

    cv2.rectangle(image, (zx1, zy1), (zx2, zy2), (255, 120, 30), 2)
    cv2.putText(image, "RESTRICTED ZONE", (zx1, max(18, zy1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 120, 30), 2)

    if result.boxes is not None:
        for box in result.boxes:
            cls_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            event = None
            if cls_id == 0:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                if zx1 < cx < zx2 and zy1 < cy < zy2:
                    label, event = "TRESPASSING", "TRESPASSING"
                else:
                    label = "PERSON"
            elif cls_id == 43:
                label, event = "DANGEROUS OBJECT: KNIFE", "DANGEROUS OBJECT"
            else:
                continue

            color = (0, 0, 255) if event else (0, 190, 90)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            cv2.putText(image, f"{label} {confidence:.0%}", (x1, max(20, y1 - 7)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            detections.append({"label": label, "confidence": round(confidence * 100, 1),
                               "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                               "event": event})
            if event:
                alert_events.append((event, confidence))

    created_alerts = []
    for event, confidence in alert_events:
        cooldown_key = (camera_code, event)
        if now_epoch - _webcam_alert_cooldowns.get(cooldown_key, 0) < 30:
            continue
        _webcam_alert_cooldowns[cooldown_key] = now_epoch
        ok, encoded = cv2.imencode(".jpg", image)
        evidence_name = None
        if ok:
            evidence_name = f"WEBCAM_{event.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
            (EVIDENCE_DIR / evidence_name).write_bytes(encoded.tobytes())

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_code = _next_alert_code(g.db)
        severity = "critical"
        cur = g.db.execute(
            "INSERT INTO alerts (alert_code,camera_id,anomaly_type,severity,confidence,evidence_path,status,created_at) "
            "VALUES (?,?,?,?,?,?, 'active',?)",
            (alert_code, camera["id"], event.replace("_", " "), severity,
             int(round(confidence * 100)), evidence_name, now))
        incident_code = _next_incident_code(g.db)
        notes = f"Created from browser webcam detection {alert_code}. Human verification required."
        g.db.execute(
            "INSERT INTO incidents (incident_code,incident_type,assigned_officer,status,camera_ref,notes,created_at) "
            "VALUES (?,?,NULL,'Open',?,?,?)",
            (incident_code, event.replace("_", " "), camera_code, notes, now))
        g.db.execute("UPDATE alerts SET incident_code=? WHERE id=?", (incident_code, cur.lastrowid))
        g.db.commit()
        created_alerts.append({"alert_code": alert_code, "incident_code": incident_code,
                               "event": event})

    return jsonify(ok=True, detections=detections, alerts_created=created_alerts,
                   restricted_zone={"x1": zx1, "y1": zy1, "x2": zx2, "y2": zy2,
                                    "width": width, "height": height},
                   supported_classes=["person", "knife"],
                   unsupported_notice="Smoke, fire and fall detection are not enabled in this model." )


@app.get("/evidence/<path:filename>")
@login_required
def get_evidence(filename):
    # Never allow path traversal; only serve files inside the evidence directory.
    if Path(filename).name != filename or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
        abort(404)
    row = g.db.execute("SELECT 1 FROM alerts WHERE evidence_path=? LIMIT 1", (filename,)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(EVIDENCE_DIR, filename, as_attachment=False)


# --------------------------------------------------------------------------
# Incidents
# --------------------------------------------------------------------------
@app.get("/api/incidents")
@login_required
def list_incidents():
    rows = g.db.execute(
        "SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
    return jsonify(incidents=[dict(r) for r in rows])


def _next_incident_code(db):
    year = datetime.now().year
    row = db.execute(
        "SELECT MAX(CAST(substr(incident_code,10) AS INTEGER)) AS mx "
        "FROM incidents WHERE incident_code LIKE ?",
        (f"INC-{year}-%",)).fetchone()
    seq = (row["mx"] + 1) if row and row["mx"] is not None else 1
    return f"INC-{year}-{seq:03d}"


@app.post("/api/incidents")
@roles_required("Security", "Admin")
def create_incident():
    d = request.get_json(silent=True) or {}
    if not d.get("incident_type"):
        return jsonify(error="incident_type is required"), 400
    code = _next_incident_code(g.db)
    status = d.get("status", "Dispatched")
    cur = g.db.execute(
        "INSERT INTO incidents (incident_code,incident_type,assigned_officer,status,camera_ref,notes,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (code, d["incident_type"], d.get("assigned_officer"), status,
         d.get("camera_ref"), d.get("notes"),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    g.db.commit()
    return jsonify(id=cur.lastrowid, incident_code=code), 201


@app.post("/api/incidents/<int:inc_id>/resolve")
@roles_required("Security", "Admin")
def resolve_incident(inc_id):
    g.db.execute("UPDATE incidents SET status='Resolved' WHERE id=?", (inc_id,))
    g.db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Reports & analytics
# --------------------------------------------------------------------------
@app.get("/api/reports/anomaly-types")
@login_required
def anomaly_types():
    rows = g.db.execute(
        "SELECT anomaly_type, COUNT(*) n FROM alerts "
        "GROUP BY anomaly_type ORDER BY n DESC").fetchall()
    total = sum(r["n"] for r in rows) or 1
    return jsonify(types=[{"type": r["anomaly_type"],
                           "count": r["n"],
                           "pct": round(r["n"] * 100 / total)} for r in rows])


@app.get("/api/reports/accuracy")
@login_required
def accuracy():
    # Derived demo metrics; in a real system these come from model eval logs.
    return jsonify(true_positive=94.2, false_positive=5.8,
                   avg_response_minutes=1.2)


# --------------------------------------------------------------------------
# Settings (Admin only)
# --------------------------------------------------------------------------
@app.get("/api/settings")
@roles_required("Admin")
def get_settings():
    rows = g.db.execute("SELECT key, value FROM settings").fetchall()
    return jsonify(settings={r["key"]: r["value"] for r in rows})


@app.put("/api/settings")
@roles_required("Admin")
def update_settings():
    d = request.get_json(silent=True) or {}
    for k, v in d.items():
        g.db.execute(
            "INSERT INTO settings (key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)))
    g.db.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
