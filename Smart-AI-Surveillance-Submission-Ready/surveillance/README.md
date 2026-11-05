# Smart AI Surveillance System — Campus Anomaly Detection

Full-stack version of the campus surveillance dashboard. The original
single HTML file has been turned into a working web application with a
**Python Flask backend**, a **SQLite database**, session-based
**authentication**, and **role-based access control (RBAC)**.

---

## 1. Architecture

```
Camera / DroidCam
        | video frames
        v
YOLOv8 + OpenCV detection worker
        | POST /api/ai/alerts + evidence image (shared token)
        v
Flask REST API (app.py)  --->  SQLite database (surveillance.db)
        ^
        | browser fetch() JSON
Dashboard UI (static/index.html, app.js)
```

- **Frontend** — `static/index.html`, `static/login.html`, `static/app.js`.
  Pure HTML + Tailwind (CDN) + vanilla JS. No data is hard-coded any more;
  every panel is populated by calling the API.
- **Backend** — `app.py` (Flask). Serves the UI and a JSON REST API.
- **Database** — `database.py` defines the schema and seeds demo data into
  `surveillance.db` (auto-created on first run). AI alerts and dashboard records
  use this same SQLite database.
- **AI ingestion** — `POST /api/ai/alerts` receives authenticated YOLO detections
  and optional JPG/PNG evidence. Each detection creates an alert and an incident.
- **Evidence** — uploaded images are stored in `evidence/` and can be viewed by
  authenticated dashboard users.

## 2. Setup & run

```bash
pip install -r requirements.txt
python database.py     # (optional) build & seed the DB; also runs automatically
python app.py          # serves on http://127.0.0.1:5000
```

Open http://127.0.0.1:5000 — you are redirected to the login page.

## 3. Demo accounts (RBAC)

| Role        | Username  | Password      | Can do                                            |
|-------------|-----------|---------------|---------------------------------------------------|
| Security    | kamogelo  | Security@123  | View all, respond to alerts, log/resolve incidents |
| Admin       | mokgadi   | Admin@123     | Everything + add/remove cameras + system settings  |
| Management  | george    | Manage@123    | View-only dashboards & reports                     |

Passwords are stored **hashed** (Werkzeug PBKDF2), never in plain text.

## 4. Database schema

| Table       | Purpose                                                        |
|-------------|----------------------------------------------------------------|
| `users`     | Login credentials + role (Security / Admin / Management)       |
| `cameras`   | Camera code, name, zone, resolution, status, AI module flag    |
| `alerts`    | AI detections: anomaly type, severity, confidence, status      |
| `incidents` | Logged incidents: type, assigned officer, status, notes        |
| `settings`  | AI thresholds (confidence cutoff, loitering time), model name  |

## 5. REST API

| Method & path                       | Role         | Description                     |
|-------------------------------------|--------------|---------------------------------|
| POST `/api/login`                   | public       | Authenticate, start session     |
| POST `/api/ai/alerts`               | AI token     | Receive standalone AI event + evidence |
| GET  `/api/camera/status`           | any          | Check browser webcam AI readiness |
| POST `/api/camera/analyze`          | any logged-in user | Analyse a browser webcam frame, return detections and record supported alerts |
| POST `/api/logout`                  | any          | End session                     |
| GET  `/api/me`                      | any          | Current user                    |
| GET  `/api/dashboard/stats`         | any          | Top metric cards                |
| GET  `/api/cameras`                 | any          | List cameras                    |
| POST `/api/cameras`                 | Admin        | Add a camera                    |
| DELETE `/api/cameras/<id>`          | Admin        | Remove a camera                 |
| GET  `/api/alerts`                  | any          | List alerts (joined w/ camera)  |
| POST `/api/alerts/<id>/dismiss`     | Security/Admin | Mark alert as false alarm     |
| GET  `/api/incidents`               | any          | List incidents                  |
| POST `/api/incidents`               | Security/Admin | Create / dispatch incident    |
| POST `/api/incidents/<id>/resolve`  | Security/Admin | Resolve incident              |
| GET  `/api/reports/anomaly-types`   | any          | Anomaly distribution            |
| GET  `/api/reports/accuracy`        | any          | Model accuracy stats            |
| GET  `/api/settings`                | Admin        | Read AI thresholds              |
| PUT  `/api/settings`                | Admin        | Update AI thresholds            |

Unauthenticated requests get **401**; wrong-role requests get **403**
(enforced server-side by the `@login_required` / `@roles_required`
decorators — the UI hiding of buttons is only cosmetic).

## 6. Connect the AI detection worker

Install the combined dependencies from `requirements.txt`, set `FLASK_SECRET_KEY`
and `AI_INGEST_TOKEN`, then start this Flask app. Start `ai_detection.py` in a
second terminal with the same `AI_INGEST_TOKEN`. See the top-level
`README-INTEGRATED.md` for exact commands and DroidCam configuration.

## 7. Tests

```bash
python smoke_test.py
```

Runs 29 end-to-end checks (auth, RBAC boundaries, CRUD, autonumbering,
static pages) using Flask's test client. All pass.

## 8. Notes & honest disclosure

- The AI worker detects the COCO person class and knife class. It does not
  reliably identify violence, intent, or every dangerous object.
- Loitering is a simple stationary-person heuristic and needs real-world
  validation. The restricted-zone rectangle must be calibrated for each view.
- The Camera Feeds page now displays the browser webcam live and posts sampled frames to the authenticated Flask analysis endpoint. The camera thumbnails in the other camera cards remain sample images; they are not separate live CCTV streams.
- The `avg_confidence` and accuracy report values still include demo semantics;
  do not present the accuracy endpoint's fixed values as measured model accuracy.
- Set strong `FLASK_SECRET_KEY` and `AI_INGEST_TOKEN` values, change demo account
  passwords, use HTTPS and a production WSGI server before real deployment.


## Browser webcam monitoring (new)

1. Use Python 3.10 or 3.11 in a virtual environment. Python 3.7.9 is too old for the current dependency set.
2. From this `surveillance` folder, install dependencies: `python -m pip install -r requirements.txt`.
3. Start the Flask app: `python app.py`. Open `http://127.0.0.1:5000` in the same computer's browser and sign in.
4. Open **Camera Feeds**, choose a registered camera record, and select **Start camera**. Allow browser webcam permission.
5. The browser shows the live webcam locally and sends a compressed frame to `/api/camera/analyze` approximately every 1.2 seconds. Flask runs the bundled YOLOv8 model and draws detections over the preview.
6. The first implementation supports the bundled COCO model's **person** and **knife** classes, plus the existing configured restricted-zone check. A person detected inside the rectangle or a detected knife creates an alert and incident, with an evidence image. The alert cooldown is 30 seconds per camera/event.
7. Select **Stop camera** or leave Camera Feeds to release the webcam. Close the standalone `ai_detection/ai_detection.py` worker while using browser webcam mode so both processes do not compete for the same webcam.

### Camera and AI limitations

- Browser camera access requires `localhost`/`127.0.0.1` or an HTTPS site, and the user must grant permission.
- The restricted-zone rectangle is currently calibrated to the right side of a 640x480 frame (the same coordinates as the existing AI worker). Recalibrate it for the actual camera view before relying on it.
- The bundled `yolov8n.pt` is a general COCO object detector. It does **not** provide smoke, fire, fall, or general danger detection. Those categories require suitable separately trained models and validation data.
- Person/knife detections can be wrong. Treat all generated alerts as prompts for human verification, not proof of an incident.
- The web endpoint analyses sampled frames, not every frame. The current browser sends about one frame every 1.2 seconds; this is a development/demo implementation, not a certified life-safety system.
- The first request loads the YOLO model and may take longer. CPU inference speed depends on the computer.
