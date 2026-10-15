"""Replay the captured startup window while preserving strict behavior-frame bounds."""
import math
from pathlib import Path


def verify_startup_readiness(row, rect, checked, classify_pixels, verify_frames, *, expected_wait_seconds=180):
    started, deadline, budget = (row.get(k) for k in ('started', 'deadline', 'wait_seconds'))
    if (type(expected_wait_seconds) is not int or not 60 <= expected_wait_seconds <= 600 or
            type(budget) is not int or budget != expected_wait_seconds or
            type(started) not in (int, float) or type(deadline) not in (int, float) or
            not math.isfinite(started) or not math.isfinite(deadline) or started < 0 or
            abs(deadline - started - budget) > 1e-6):
        raise ValueError('explicit captured bounded startup-readiness window required')
    frames = row.get('frames')
    if not isinstance(frames, list) or len(frames) < 3:
        raise ValueError('three actual stable baseline captures required')
    previous_after, seen = started, set()
    for frame in frames:
        path = checked(frame.get('path', ''), frame.get('sha256'))
        before, after = frame.get('before'), frame.get('after')
        if (str(path) in seen or type(before) not in (int, float) or type(after) not in (int, float) or
                not math.isfinite(before) or not math.isfinite(after) or
                before < previous_after or after < before or after > deadline):
            raise ValueError('invalid startup-readiness chronology/identity/deadline')
        try:
            actual, error = classify_pixels(path, rect), None
        except ValueError as exception:
            actual, error = 'not-baseline', str(exception)
        if frame.get('kind') != actual or frame.get('precondition_error') != error:
            raise ValueError('startup-readiness classification differs from actual capture')
        seen.add(str(path)); previous_after = after
    # Unchanged verifier retains <=3s per frame, real pixels and stable final off.
    return verify_frames(frames[-3:], rect, 'off')
