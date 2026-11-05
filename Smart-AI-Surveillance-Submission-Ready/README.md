# Smart AI Surveillance System — Integrated Project

This package combines the supplied Flask dashboard/database with the original YOLOv8/OpenCV detection code. The recommended demonstration mode is the browser webcam inside the dashboard.

## Project structure

- `surveillance/` — Flask application, HTML/CSS/JavaScript frontend, authentication/RBAC, SQLite database, alerts, incidents, reports, settings and evidence storage.
- `ai_detection/` — optional standalone OpenCV/YOLOv8 camera worker and bundled `yolov8n.pt` weights.
- `SUBMISSION-READINESS.md` — implemented features, limitations and local verification checklist.

## Recommended setup: webcam inside the dashboard

Use Python 3.10 or 3.11. On Windows PowerShell, open a terminal in the project root:

```powershell
cd surveillance
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:FLASK_SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

Open `http://127.0.0.1:5000`, sign in, select **Camera Feeds**, choose a registered camera profile and click **Start camera**. Allow webcam permission in the browser. For this mode, only the Flask process is required; do not start the standalone worker using the same webcam.

The browser displays the camera feed and sends a compressed frame about every 1.2 seconds to the authenticated Flask endpoint `POST /api/camera/analyze`. Flask runs YOLOv8, returns detection coordinates, and the frontend draws the boxes over the live feed. Supported events create alerts, linked incidents and evidence records in SQLite.

Camera access works on `localhost`/`127.0.0.1` or an HTTPS origin. Close other applications that may be using the webcam.

## Optional: standalone OpenCV camera worker

The optional worker can use a webcam index or compatible RTSP/HTTP stream. Start Flask first, then open a second terminal from the project root:

```powershell
cd ai_detection
..\surveillance\.venv\Scripts\Activate.ps1
$env:AI_INGEST_TOKEN="use-a-long-random-token"
$env:AI_API_URL="http://127.0.0.1:5000"
$env:CAMERA_CODE="CAM-01"
$env:CAMERA_SOURCE="0"
python ai_detection.py
```

For this mode, set the same `AI_INGEST_TOKEN` in the Flask terminal before starting Flask. Do not run this worker at the same time as browser webcam mode if both use the same physical webcam.

## Demo accounts

- Security: `kamogelo` / `Security@123`
- Admin: `mokgadi` / `Admin@123`
- Management: `george` / `Manage@123`

These are demonstration credentials. Change them before any deployment beyond a controlled local demo.

## Current detection scope

The bundled COCO YOLOv8n model supports the person and knife classes used by the browser webcam endpoint. The system applies a configured restricted-zone rule to detected people. The optional standalone worker also contains a basic loitering heuristic.

**Smoke, fire, fall, violence and general all-danger detection are not implemented by the bundled model.** They require suitable separately trained models/algorithms and validation. Other camera cards are registered camera profiles with sample thumbnails; this build does not provide simultaneous live CCTV streams from multiple cameras. The webcam analysis uses sampled frames rather than every video frame. All alerts require human verification.

## Test

From the `surveillance/` folder run:

```powershell
python smoke_test.py
```

The smoke test rebuilds the seeded demo SQLite database at the end. Back up any database containing records you need before running it.

## Security and deployment

This is a local academic demonstration build, not a certified life-safety product or production deployment. Before institutional deployment, use HTTPS, a production WSGI server, unique strong secrets, changed demo passwords, access controls, evidence retention rules and appropriate privacy approval. Do not present demo report accuracy values as measured model performance.
