"""
qr_scan.py
-----------
Opens the webcam in a focused single-scan mode: detects exactly one
QR code (containing a person_code), marks attendance, shows a clear
on-screen confirmation, then closes automatically.
"""

import cv2
import time
import database as db
from recognize import speak


def run_qr_scan(camera_index=0, timeout_seconds=30):
    cam = cv2.VideoCapture(camera_index)
    detector = cv2.QRCodeDetector()

    if not cam.isOpened():
        raise RuntimeError("Could not open webcam.")

    print("[INFO] Waiting for a QR code. Press Q to cancel.")
    speak("Show your QR code to the camera")

    marked = []
    result_person = None
    result_action = None
    confirm_until = None  # time until which we keep showing the confirmation
    start_time = time.time()

    WINDOW = "QR Scan - Show your code"

    while True:
        ret, frame = cam.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        overlay = frame.copy()

        if confirm_until is None:
            # ---- Waiting state: look for a QR code ----
            qr_text, points, _ = detector.detectAndDecode(frame)

            # ---- Dim everything outside the guide box, keep inside bright/clear ----
            box_size = min(h, w) // 2
            cx, cy = w // 2, h // 2
            x1, y1 = cx - box_size // 2, cy - box_size // 2
            x2, y2 = cx + box_size // 2, cy + box_size // 2

            dimmed = (overlay * 0.25).astype(overlay.dtype)  # darken the whole frame
            dimmed[y1:y2, x1:x2] = overlay[y1:y2, x1:x2]      # restore original brightness inside the box
            overlay = dimmed

            # Border around the focus box
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 200, 255), 2)
            cv2.putText(overlay, "Show QR code inside the box", (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

            if points is not None:
                pts = points.astype(int).reshape(-1, 2)
                for i in range(len(pts)):
                    cv2.line(overlay, tuple(pts[i]), tuple(pts[(i + 1) % len(pts)]), (0, 255, 0), 3)

            if qr_text:
                qr_text = qr_text.strip()
                person = db.get_person_by_qr(qr_text) or db.get_person_by_code(qr_text)

                if person:
                    action, _ = db.mark_attendance(person["id"])
                    result_person = person
                    result_action = action
                    marked.append(qr_text)

                    if action == "in":
                        speak(f"Welcome, {person['name']}. Checked in.")
                    elif action == "out":
                        speak(f"Goodbye, {person['name']}. Checked out.")
                    else:
                        speak(f"{person['name']}, you are already checked in and out today")

                    confirm_until = time.time() + 2.5  # show result for 2.5s then close
                else:
                    speak("QR code not recognized")
                    cv2.putText(overlay, "QR not recognized", (20, h - 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Timeout if nobody shows a code
            if time.time() - start_time > timeout_seconds:
                print("[INFO] QR scan timed out.")
                break

        else:
            # ---- Confirmation state: show result and auto-close ----
            overlay[:] = (20, 20, 20)
            color = (0, 255, 0) if result_action in ("in", "out") else (0, 200, 255)
            label = {
                "in": f"CHECKED IN: {result_person['name']}",
                "out": f"CHECKED OUT: {result_person['name']}",
                "done": f"{result_person['name']} ALREADY MARKED TODAY",
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
    run_qr_scan()