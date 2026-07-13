"""
voice_enroll.py
----------------
Records a few voice samples of a person saying their name, to build
their voiceprint for future speaker verification.
"""

import os
import time
import speech_recognition as sr
from recognize import speak
import voice_auth
from voice_ui import VoiceStatusWindow

TEMP_DIR = "voice_samples_temp"


def enroll_voice(person_code, name, num_samples=3):
    os.makedirs(TEMP_DIR, exist_ok=True)
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    wav_paths = []

    speak(f"Let's record your voice, {name}. You will say your name {num_samples} times.")
    time.sleep(1)

    i = 0
    while i < num_samples:
        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.7)
                speak(f"Recording {i + 1}. Please speak now.")
                time.sleep(0.3)

                with VoiceStatusWindow(f"Recording {i + 1} of {num_samples}..."):
                    audio = recognizer.listen(source, timeout=8, phrase_time_limit=4)

            wav_path = os.path.join(TEMP_DIR, f"{person_code}_{i}.wav")
            with open(wav_path, "wb") as f:
                f.write(audio.get_wav_data())
            wav_paths.append(wav_path)
            i += 1

        except sr.WaitTimeoutError:
            speak("I didn't hear anything, let's try that again.")
            continue

    voice_auth.save_voiceprint(person_code, wav_paths)

    for p in wav_paths:
        os.remove(p)

    speak("Voice enrollment complete.")
    return True