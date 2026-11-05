"""YOLOv8/OpenCV detection worker connected to the FullStack Flask API.

Run the Flask dashboard first, then run this worker in a second terminal.
"""
import os
import time
import math
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = BASE_DIR / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = BASE_DIR / "yolov8n.pt"

API_BASE_URL = os.getenv("AI_API_URL", "http://127.0.0.1:5000").rstrip("/")
AI_INGEST_TOKEN = os.getenv("AI_INGEST_TOKEN", "")
CAMERA_CODE = os.getenv("CAMERA_CODE", "CAM-01")
CAMERA_VALUE = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(CAMERA_VALUE) if CAMERA_VALUE.isdigit() else CAMERA_VALUE
CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE", "0.45"))
LOITER_SECONDS = int(os.getenv("LOITER_SECONDS", "10"))
EVENT_COOLDOWN_SECONDS = int(os.getenv("EVENT_COOLDOWN_SECONDS", "45"))
# Coordinates are based on a 640x480 frame; adjust for your camera view.
RESTRICTED_ZONE = (450, 50, 630, 430)

if not AI_INGEST_TOKEN:
    raise SystemExit("Set AI_INGEST_TOKEN in your environment before starting the detector.")
if not MODEL_PATH.exists():
    raise SystemExit(f"YOLO model not found: {MODEL_PATH}")

model = YOLO(str(MODEL_PATH))
cap = cv2.VideoCapture(CAMERA_SOURCE)
if not cap.isOpened():
    raise SystemExit(f"Cannot open camera source {CAMERA_SOURCE}. Try CAMERA_SOURCE=1 or your DroidCam stream URL.")
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

last_sent = {}
loiter_started = {}
previous_centres = {}


def send_detection(event_name, confidence, frame):
    """Save a local evidence copy and upload it with the alert to Flask."""
    stamp = int(time.time())
    filename = f"{event_name}_{stamp}.jpg"
    local_path = EVIDENCE_DIR / filename
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        print("Could not encode evidence image")
        return
    image_bytes = encoded.tobytes()
    local_path.write_bytes(image_bytes)

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/ai/alerts",
            headers={"X-AI-Token": AI_INGEST_TOKEN},
            data={"camera": CAMERA_CODE, "event": event_name,
                  "confidence": f"{confidence * 100:.1f}"},
            files={"evidence": (filename, image_bytes, "image/jpeg")},
            timeout=10,
        )
        if response.ok:
            print(f"[SENT] {event_name}: {response.json()}")
        else:
            print(f"[API ERROR] {response.status_code}: {response.text[:300]}")
    except requests.RequestException as exc:
        print(f"[API CONNECTION ERROR] {exc}. Evidence remains at {local_path}")


def allowed_to_send(event_name):
    now = time.time()
    if now - last_sent.get(event_name, 0) < EVENT_COOLDOWN_SECONDS:
        return False
    last_sent[event_name] = now
    return True


print(f"AI detector running | camera={CAMERA_CODE} | source={CAMERA_SOURCE} | API={API_BASE_URL}")
print("Press Q in the video window to stop.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera frame unavailable; retrying...")
            time.sleep(0.2)
            continue

        # ByteTrack IDs allow the loitering timer to follow a person across frames.
        result = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0, 43],
                             conf=CONFIDENCE_THRESHOLD, verbose=False)[0]
        rx1, ry1, rx2, ry2 = RESTRICTED_ZONE
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (255, 0, 0), 2)
        cv2.putText(frame, "RESTRICTED ZONE", (rx1, max(20, ry1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 0), 2)

        boxes = result.boxes
        if boxes is not None:
            ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(boxes)
            for box, track_id in zip(boxes, ids):
                cls_id = int(box.cls.item())
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                event_name = None
                label = None
                color = (0, 200, 0)

                if cls_id == 0:  # COCO person class
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if rx1 < cx < rx2 and ry1 < cy < ry2:
                        label, event_name, color = "TRESPASSING", "TRESPASSING", (0, 0, 255)
                    elif track_id is not None:
                        old = previous_centres.get(track_id)
                        if old is not None and math.hypot(cx - old[0], cy - old[1]) < 8:
                            loiter_started.setdefault(track_id, time.time())
                            if time.time() - loiter_started[track_id] >= LOITER_SECONDS:
                                label, event_name, color = "LOITERING", "LOITERING", (0, 165, 255)
                        else:
                            loiter_started.pop(track_id, None)
                        previous_centres[track_id] = (cx, cy)
                    label = label or "PERSON"
                elif cls_id == 43:  # COCO class 43 = knife
                    label, event_name, color = "DANGEROUS OBJECT: KNIFE", "DANGEROUS OBJECT", (0, 0, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label} {confidence:.0%}", (x1, max(20, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                if event_name and allowed_to_send(event_name):
                    send_detection(event_name, confidence, frame.copy())

        cv2.imshow("Smart AI Surveillance - Live Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("AI detector stopped.")
