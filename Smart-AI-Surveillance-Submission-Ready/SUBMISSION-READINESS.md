# Submission Readiness — Smart AI Surveillance System

## Frontend-to-backend connection

The browser dashboard is served by Flask from `surveillance/static/`. The **Camera Feeds** page contains the live webcam element and JavaScript controller. When the user starts the camera, the browser requests webcam permission using `getUserMedia()`, displays the live stream, captures a JPEG frame approximately every 1.2 seconds, and posts it to the authenticated Flask endpoint `POST /api/camera/analyze`.

Flask loads the bundled YOLOv8 model when needed, analyses the submitted frame, returns detection coordinates and labels as JSON, and the frontend draws those detections over the live preview. Supported security events create an alert and a linked incident in the same SQLite database used by the dashboard. Evidence images are stored under `surveillance/evidence/` and served to authenticated users.

The frontend also calls `GET /api/camera/status` to show whether the model file and required AI packages are available on the server.

## Implemented in this package

- Flask dashboard and static frontend.
- Session-based login and role-based access controls.
- SQLite database and seeded demo records.
- Browser webcam preview with start/stop controls.
- Sampled-frame analysis endpoint connected to the frontend.
- YOLOv8 person and knife class inference.
- Configured restricted-zone check for detected people.
- Detection boxes and labels drawn over the browser video.
- Alert and incident creation with evidence capture for supported events.
- AI readiness endpoint and updated setup documentation.

## Not implemented / not validated

- Smoke detection.
- Fire/flame detection.
- Fall detection.
- Violence or fight recognition.
- Reliable detection of all weapon types.
- Full multi-camera CCTV streaming. Other camera profile cards still use sample thumbnails.
- Certified emergency/life-safety monitoring.
- Production deployment hardening.

The bundled YOLOv8n weights are a general COCO model. The current webcam endpoint limits inference to the COCO `person` and `knife` classes. The restricted-zone rectangle is a fixed proportional region and must be calibrated to the actual camera view. Detection results can be false positives or false negatives and require human review.

## Local test status

Static Python compilation (`py_compile`) and JavaScript syntax validation (`node --check`) passed when this package was prepared. The complete Flask/YOLO runtime test was **not run in the preparation environment** because Flask, Werkzeug and Ultralytics were not installed there. Install `surveillance/requirements.txt` and run `python smoke_test.py` from the `surveillance/` directory on the target computer. The smoke test rebuilds the demo SQLite database; back up any database containing important records first.

## Before presentation/submission

1. Install dependencies in Python 3.10 or 3.11.
2. Run the Flask app and verify login.
3. Confirm browser permission and live webcam preview.
4. Confirm a person appears with a detection box.
5. Calibrate the restricted-zone rectangle for the webcam position and test an entry event.
6. If testing knife detection, use a safe, controlled test image/video rather than a real weapon.
7. Confirm an alert appears in the dashboard and a linked incident is stored.
8. Do not claim smoke, fire, fall or all-danger detection as implemented.
9. Change demo passwords and secret keys before any deployment beyond a controlled local demonstration.
