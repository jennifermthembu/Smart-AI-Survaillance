# Smart AI Surveillance System — Integrated Build

This package combines the FullStack Flask dashboard with the YOLOv8/OpenCV detection worker.

## Architecture

Camera / DroidCam -> YOLOv8 + OpenCV worker -> authenticated Flask AI-ingestion API -> SQLite -> dashboard alerts and incidents.

The FullStack Flask application remains the main application and owns the single SQLite database. The old MySQL code from the AI project is not used in this integrated build.

## 1. Requirements

- Python 3.10 or 3.11 recommended
- Windows, Linux or macOS
- A webcam, DroidCam virtual camera, or supported RTSP/HTTP camera stream
- Internet access for the first Python package/model setup if dependencies are not already installed

## 2. Install

Open a terminal in `surveillance/`:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The YOLO weights `ai_detection/yolov8n.pt` are included in the package.

## 3. Configure shared secret

Set the SAME secret in both processes. Do not commit the real value to Git.

Windows PowerShell (run in each terminal):
```powershell
$env:FLASK_SECRET_KEY="use-a-long-random-secret-for-flask"
$env:AI_INGEST_TOKEN="use-a-different-long-random-token"
```

Linux/macOS:
```bash
export FLASK_SECRET_KEY='use-a-long-random-secret-for-flask'
export AI_INGEST_TOKEN='use-a-different-long-random-token'
```

## 4. Start the dashboard/backend first

```bash
cd surveillance
python app.py
```

Open http://127.0.0.1:5000 and sign in. Demo accounts are listed in `surveillance/README.md`; change them before real deployment.

## 5. Start the AI detection worker in a second terminal

Activate the same virtual environment, set the same `AI_INGEST_TOKEN`, then:

```bash
cd ai_detection
python ai_detection.py
```

Defaults: camera code `CAM-01`, camera index `0`, Flask API `http://127.0.0.1:5000`.

### DroidCam / other camera index

If DroidCam is not camera index 0, set the correct index before starting the worker:

PowerShell:
```powershell
$env:CAMERA_SOURCE="1"
$env:CAMERA_CODE="CAM-01"
$env:AI_API_URL="http://127.0.0.1:5000"
python ai_detection.py
```

Linux/macOS:
```bash
CAMERA_SOURCE=1 CAMERA_CODE=CAM-01 AI_API_URL=http://127.0.0.1:5000 python ai_detection.py
```

For a network camera, set `CAMERA_SOURCE` to its RTSP/HTTP stream URL instead of a number. The corresponding camera code must already exist in the dashboard database.

## 6. What was integrated

1. Added `POST /api/ai/alerts` to Flask. It accepts AI detections and evidence uploads using the shared `X-AI-Token` header.
2. The endpoint maps `CAM-01` (or another camera code) to the camera row in SQLite.
3. It creates an alert and automatically opens a linked incident.
4. Evidence images are stored in `surveillance/evidence/` and served only to authenticated users through `/evidence/<filename>`.
5. Added an `evidence_path` database column with a safe migration for existing databases.
6. Updated the dashboard alert feed to show a View captured evidence link when an image is attached.
7. Replaced the AI worker's old `/alert` request and old MySQL integration with multipart upload to the FullStack Flask API.
8. Added event cooldowns and persistent YOLO tracking IDs for a more stable loitering timer.

## 7. Important limitations

- YOLOv8n is a general COCO object detector. It detects people and the COCO knife class; it does NOT reliably identify violence, intent, or every dangerous object. Do not describe those capabilities as implemented unless a suitable trained model is added and validated.
- Loitering is a simple stationary-person heuristic, not a validated behavioural classifier.
- The restricted-zone rectangle is currently configured for a 640x480 frame. Adjust `RESTRICTED_ZONE` in `ai_detection.py` to match the camera view.
- The Camera Feeds page includes a browser webcam preview and sampled-frame AI analysis. Other camera-card thumbnails remain sample images; this is not a multi-camera CCTV streaming implementation.
- Dashboard reports' accuracy values remain demo metrics and must not be presented as measured model accuracy.
- This is a local integration build. Before public/institutional deployment, use HTTPS, a production WSGI server, strong unique secrets, changed demo passwords, network restrictions, retention controls and appropriate privacy approval.

## 8. Test

From `surveillance/` run:
```bash
python smoke_test.py
```

The smoke test rebuilds the demo database at the end. Back up `surveillance.db` first if it contains data you need.
