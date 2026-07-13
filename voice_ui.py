"""
voice_ui.py
------------
Small visual status window (using OpenCV) shown while listening for
voice input, so the user gets a clear visual cue of when to speak.
"""

import cv2
import numpy as np
import threading
import time

WINDOW_NAME = "Voice Status"


def _run_window(stop_event, message, color):
    start = time.time()
    while not stop_event.is_set():
        img = np.zeros((220, 560, 3), dtype=np.uint8)
        img[:] = (25, 25, 30)

        # Pulsing circle to indicate "live" listening
        radius = 18 + int(6 * abs((time.time() - start) % 1 - 0.5) * 2)
        cv2.circle(img, (60, 110), radius, color, -1)

        cv2.putText(img, message, (110, 100), cv2.FONT_HERSHEY_SIMPLEX,
                    0.75, (255, 255, 255), 2)
        cv2.putText(img, "Speak clearly into the microphone", (110, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        cv2.imshow(WINDOW_NAME, img)
        cv2.waitKey(50)

    cv2.destroyWindow(WINDOW_NAME)


class VoiceStatusWindow:
    """Usage:
        with VoiceStatusWindow("Recording 1... Speak now"):
            audio = recognizer.listen(source, ...)
    """
    def __init__(self, message, color=(0, 200, 255)):
        self.message = message
        self.color = color
        self.stop_event = threading.Event()
        self.thread = None

    def __enter__(self):
        self.thread = threading.Thread(
            target=_run_window, args=(self.stop_event, self.message, self.color), daemon=True
        )
        self.thread.start()
        time.sleep(0.15)  # give the window a moment to appear
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)