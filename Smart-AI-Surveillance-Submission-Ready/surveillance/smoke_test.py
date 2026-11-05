"""End-to-end smoke test using Flask's test client (no network listener).
Exercises auth, RBAC, and every CRUD path, then prints a PASS/FAIL summary.
"""
import json
import os
from io import BytesIO
os.environ["AI_INGEST_TOKEN"] = "test-ai-token"
import database
import app as application

database.init_db(force=True)  # fresh, seeded DB
c = application.app.test_client()
fails = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        fails.append(name)


def login(u, p):
    return c.post("/api/login", json={"username": u, "password": p})


# --- AI ingestion is protected and writes alert + incident + evidence ---
check("AI ingestion without token -> 401",
      c.post("/api/ai/alerts", data={"camera": "CAM-01", "event": "TRESPASSING"}).status_code == 401)
r = c.post("/api/ai/alerts", headers={"X-AI-Token": "test-ai-token"},
           data={"camera": "CAM-01", "event": "TRESPASSING", "confidence": "91.5",
                 "evidence": (BytesIO(b"fake-jpeg-bytes"), "test.jpg")},
           content_type="multipart/form-data")
check("AI ingestion -> 201", r.status_code == 201)
ai_result = r.get_json() if r.status_code == 201 else {}
if r.status_code == 201:
    check("AI ingestion creates linked incident", bool(ai_result.get("incident_code")))
    check("AI ingestion stores evidence", bool(ai_result.get("evidence_url")))

# --- unauthenticated is blocked ---
check("unauth /api/me -> 401", c.get("/api/me").status_code == 401)
check("unauth webcam status -> 401", c.get("/api/camera/status").status_code == 401)
check("unauth webcam analysis -> 401", c.post("/api/camera/analyze").status_code == 401)
check("bad login -> 401", login("kamogelo", "wrong").status_code == 401)

# --- Security role ---
r = login("kamogelo", "Security@123")
check("security login -> 200", r.status_code == 200)
check("security role", r.get_json()["user"]["role"] == "Security")
webcam_status = c.get("/api/camera/status")
check("webcam AI status endpoint responds", webcam_status.status_code == 200)
if webcam_status.status_code == 200:
    webcam_data = webcam_status.get_json()
    check("webcam status reports supported classes", webcam_data.get("supported_classes") == ["person", "knife"])

stats = c.get("/api/dashboard/stats").get_json()
check("dashboard stats has feeds", stats["connected_feeds"] == 4)
check("active anomalies include seeded + AI alert", stats["active_anomalies"] == 3)

cams = c.get("/api/cameras").get_json()["cameras"]
check("4 cameras seeded", len(cams) == 4)

alerts = c.get("/api/alerts").get_json()["alerts"]
check("alerts joined with camera", all("cam_code" in a for a in alerts))
check("AI alert links to its incident", any(a.get("incident_code") for a in alerts))
if ai_result.get("evidence_url"):
    check("evidence requires login and is served", c.get(ai_result["evidence_url"]).status_code == 200)

# security cannot add camera (admin only)
check("security add camera -> 403",
      c.post("/api/cameras", json={"code": "CAM-09", "name": "x", "zone": "z"}).status_code == 403)

# security can create + resolve incident
r = c.post("/api/incidents", json={"incident_type": "Test Breach",
                                    "assigned_officer": "Officer William",
                                    "camera_ref": "CAM-01"})
check("create incident -> 201", r.status_code == 201)
new_code = r.get_json()["incident_code"]
check("incident code autonumbered", new_code.startswith("INC-"))
new_id = r.get_json()["id"]
check("resolve incident -> 200",
      c.post(f"/api/incidents/{new_id}/resolve").status_code == 200)

# dismiss an active alert
aid = [a["id"] for a in alerts if a["status"] == "active"][0]
check("dismiss alert -> 200", c.post(f"/api/alerts/{aid}/dismiss").status_code == 200)
check("active anomalies drops after dismiss",
      c.get("/api/dashboard/stats").get_json()["active_anomalies"] == 2)

# security blocked from settings
check("security settings -> 403", c.get("/api/settings").status_code == 403)

# reports
rt = c.get("/api/reports/anomaly-types").get_json()["types"]
check("anomaly types returned", len(rt) >= 1 and "pct" in rt[0])

c.post("/api/logout")

# --- Admin role ---
login("mokgadi", "Admin@123")
r = c.post("/api/cameras", json={"code": "CAM-05", "name": "Gym Hall", "zone": "South"})
check("admin add camera -> 201", r.status_code == 201)
check("admin duplicate camera -> 400",
      c.post("/api/cameras", json={"code": "CAM-05", "name": "dup", "zone": "x"}).status_code == 400)
check("admin get settings -> 200", c.get("/api/settings").status_code == 200)
check("admin update settings -> 200",
      c.put("/api/settings", json={"confidence_cutoff": "85"}).status_code == 200)
check("setting persisted",
      c.get("/api/settings").get_json()["settings"]["confidence_cutoff"] == "85")
check("admin delete camera -> 200",
      c.delete(f"/api/cameras/{r.get_json()['id']}").status_code == 200)
c.post("/api/logout")

# --- Management role (view-only) ---
login("george", "Manage@123")
check("mgmt can read dashboard", c.get("/api/dashboard/stats").status_code == 200)
check("mgmt cannot create incident -> 403",
      c.post("/api/incidents", json={"incident_type": "x"}).status_code == 403)
check("mgmt cannot add camera -> 403",
      c.post("/api/cameras", json={"code": "CAM-06", "name": "x", "zone": "z"}).status_code == 403)
check("mgmt cannot open settings -> 403", c.get("/api/settings").status_code == 403)

# --- static pages served ---
check("index served", c.get("/").status_code == 200)
check("login page served", c.get("/login").status_code == 200)
check("app.js served", c.get("/static/app.js").status_code == 200)
index_html = c.get("/").get_data(as_text=True)
app_js = c.get("/static/app.js").get_data(as_text=True)
check("frontend includes live webcam video element", 'id="webcamVideo"' in index_html)
check("frontend posts webcam frames to Flask analysis endpoint", "'/api/camera/analyze'" in app_js)
check("frontend checks backend AI readiness", "'/api/camera/status'" in app_js)

print("\n" + ("ALL TESTS PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))

# reset DB back to clean seeded state for delivery; remove test evidence only.
for evidence_file in application.EVIDENCE_DIR.glob("*test*"):
    if evidence_file.is_file():
        evidence_file.unlink()
database.init_db(force=True)
