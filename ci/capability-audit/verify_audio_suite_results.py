"""Validate actual PCM/state observations; algorithm/device paths excluded."""
import json

SCOPE = "AudioSuite PCM passthrough, not algorithm plugins/download"


def verify(text, code):
    if type(code) is not int or code != 0:
        raise ValueError("AudioSuite guest process did not exit successfully")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("one fresh complete AudioSuite PCM result required")
    row = rows[0]
    expected = {"scope", "cycles", "verified_samples", "input_callbacks", "invalid_state_boundary", "pass"}
    if (set(row) != expected or row.get("scope") != SCOPE or row.get("pass") is not True or
            row.get("invalid_state_boundary") is not True or
            type(row.get("cycles")) is not int or row["cycles"] != 2 or
            type(row.get("verified_samples")) is not int or row["verified_samples"] != 3840 or
            type(row.get("input_callbacks")) is not int or row["input_callbacks"] < 2):
        raise ValueError("AudioSuite PCM data/state/boundary validation failed")
    return {"scope": SCOPE, "observations": row, "algorithm_plugins_tested": False,
            "realtime_audio_device_tested": False}
