"""
recognize.py
-------------
Opens the webcam in a focused single-scan mode: detects exactly one
registered face, marks attendance, shows a clear on-screen
confirmation, then closes automatically.
"""

import cv2
import os
import json
import threading
import time
import pyttsx3
import database as db

TRAINER_FILE = os.path.join("trainer", "trainer.yml")
LABELS_FILE = os.path.join("trainer", "labels.json")
FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

CONFIDENCE_THRESHOLD = 70


def load_model():
    if not os.path.exists(TRAINER_FILE) or not os.path.exists(LABELS_FILE):
        raise RuntimeError("Model not found. Run train_model.py first.")

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(TRAINER_FILE)

    with open(LABELS_FILE, "r") as f:
        raw_labels = json.load(f)
    label_map = {int(k): v for k, v in raw_labels.items()}

    return recognizer, label_map


def speak(text):
    """Speak text in a separate thread so the camera loop doesn't freeze."""
    def _run():
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    threading.Thread(target=_run, daemon=True).start()


def run_recognition(camera_index=0, timeout_seconds=30):
    recognizer, label_map = load_model()
    face_detector = cv2.CascadeClassifier(FACE_CASCADE_PATH)
    cam = cv2.VideoCapture(camera_index)

    if not cam.isOpened():
        raise RuntimeError("Could not open webcam.")

    print("[INFO] Waiting for a face. Press Q to cancel.")
    speak("Look at the camera")

    marked = []
    result_name = None
    result_action = None
    confirm_until = None
    start_time = time.time()

    WINDOW = "Face Scan - Look at the camera"

    while True:
        ret, frame = cam.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        overlay = frame.copy()

        if confirm_until is None:
            # ---- Waiting state: look for a recognized face ----
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)

            for (x, y, fw, fh) in faces:
                face_img = cv2.resize(gray[y:y + fh, x:x + fw], (200, 200))
                label_id, confidence = recognizer.predict(face_img)

                if confidence < CONFIDENCE_THRESHOLD and label_id in label_map:
                    person_code = label_map[label_id]["person_code"]
                    name = label_map[label_id]["name"]
                    color = (0, 255, 0)
                    display_text = f"{name} ({confidence:.0f})"

                    person = db.get_person_by_code(person_code)
                    if person:
                        action, _ = db.mark_attendance(person["id"])
                        marked.append(person_code)
                        result_name = name
                        result_action = action

                        if action == "in":
                            speak(f"Welcome, {name}. Checked in.")
                        elif action == "out":
                            speak(f"Goodbye, {name}. Checked out.")
                        else:
                            speak(f"{name}, you are already checked in and out today")

                        confirm_until = time.time() + 2.5

                    cv2.rectangle(overlay, (x, y), (x + fw, y + fh), color, 2)
                    cv2.putText(overlay, display_text, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    break  # only handle the first confidently recognized face
                else:
                    cv2.rectangle(overlay, (x, y), (x + fw, y + fh), (0, 0, 255), 2)
                    cv2.putText(overlay, "Unknown", (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.putText(overlay, "Position your face in the camera", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

            if time.time() - start_time > timeout_seconds:
                print("[INFO] Face scan timed out.")
                break

        else:
            # ---- Confirmation state: show result and auto-close ----
            overlay[:] = (20, 20, 20)
            color = (0, 255, 0) if result_action in ("in", "out") else (0, 200, 255)
            label = {
                "in": f"CHECKED IN: {result_name}",
                "out": f"CHECKED OUT: {result_name}",
                "done": f"{result_name} ALREADY MARKED TODAY",
            }.get(result_action, "Done")

            cv2.putText(overlay, label, (30, h // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, color, 2)

            if time.time() >= confirm_until:
                break

        cv2.imshow(WINDOW, overlay)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    return marked


if __name__ == "__main__":
    run_recognition()