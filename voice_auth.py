"""
voice_auth.py
--------------
Builds and verifies voiceprints (speaker verification) using MFCC
features so that attendance can only be marked by the actual
registered person's voice, not just by speaking their name.
"""

import os
import numpy as np
import librosa

VOICEPRINT_DIR = "voiceprints"
SIMILARITY_THRESHOLD = 0.82  # tune this after testing (0.75-0.90 typical)


def _extract_features(wav_path):
    y, sr = librosa.load(wav_path, sr=16000)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    delta = librosa.feature.delta(mfcc)
    combined = np.vstack([mfcc, delta])
    return np.mean(combined, axis=1)


def save_voiceprint(person_code, wav_paths):
    """Average features from multiple enrollment recordings into one voiceprint."""
    features = [_extract_features(p) for p in wav_paths]
    voiceprint = np.mean(features, axis=0)
    os.makedirs(VOICEPRINT_DIR, exist_ok=True)
    np.save(os.path.join(VOICEPRINT_DIR, f"{person_code}.npy"), voiceprint)


def has_voiceprint(person_code):
    return os.path.exists(os.path.join(VOICEPRINT_DIR, f"{person_code}.npy"))


def verify_voice(person_code, wav_path):
    """Returns (is_match: bool, similarity: float)."""
    voiceprint_path = os.path.join(VOICEPRINT_DIR, f"{person_code}.npy")
    if not os.path.exists(voiceprint_path):
        return False, 0.0

    stored = np.load(voiceprint_path)
    current = _extract_features(wav_path)

    similarity = np.dot(stored, current) / (
        np.linalg.norm(stored) * np.linalg.norm(current)
    )
    return similarity >= SIMILARITY_THRESHOLD, float(similarity)