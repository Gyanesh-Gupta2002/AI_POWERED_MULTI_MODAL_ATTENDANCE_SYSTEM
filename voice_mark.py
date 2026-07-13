"""
voice_mark.py
--------------
Listens to the microphone, matches the spoken name against
registered people, verifies the speaker's voiceprint, and marks
attendance (check-in / check-out).
"""

import speech_recognition as sr
import difflib
import os
import database as db
import voice_auth
from recognize import speak
from voice_ui import VoiceStatusWindow

TEMP_DIR = "voice_samples_temp"


def get_name_match(spoken_name, people):
    names = [p["name"] for p in people]
    matches = difflib.get_close_matches(
        spoken_name.lower(), [n.lower() for n in names], n=1, cutoff=0.6
    )
    if matches:
        idx = [n.lower() for n in names].index(matches[0])
        return people[idx]
    return None


def listen_and_mark(timeout=5, phrase_time_limit=5):
    os.makedirs(TEMP_DIR, exist_ok=True)
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    people = [dict(p) for p in db.get_all_people()]

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        speak("Please say your name followed by present")
        print("[VOICE] Listening...")
        try:
            with VoiceStatusWindow("Listening... Say your name"):
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            speak("No speech detected")
            return None, "timeout"

    temp_wav = os.path.join(TEMP_DIR, "current_attempt.wav")
    with open(temp_wav, "wb") as f:
        f.write(audio.get_wav_data())

    try:
        text = recognizer.recognize_google(audio)
        print(f"[VOICE] Heard: {text}")
    except sr.UnknownValueError:
        speak("Sorry, I could not understand")
        return None, "not_understood"
    except sr.RequestError:
        speak("Speech service unavailable")
        return None, "service_error"

    spoken_name = text.lower().replace("present", "").strip()
    person = get_name_match(spoken_name, people)

    if not person:
        speak("Sorry, I could not find that name")
        return None, "no_match"

    if not voice_auth.has_voiceprint(person["person_code"]):
        speak(f"No voice profile found for {person['name']}. Please enroll first.")
        return person, "no_voiceprint"

    is_match, similarity = voice_auth.verify_voice(person["person_code"], temp_wav)
    print(f"[VOICE] Similarity for {person['name']}: {similarity:.2f}")

    if not is_match:
        speak("Voice does not match the registered person. Attendance denied.")
        return person, "voice_mismatch"

    action, _ = db.mark_attendance(person["id"])

    if action == "in":
        speak(f"Welcome, {person['name']}. Checked in.")
        return person, "marked_in"
    elif action == "out":
        speak(f"Goodbye, {person['name']}. Checked out.")
        return person, "marked_out"
    else:
        speak(f"{person['name']}, you are already checked in and out today")
        return person, "already_done"