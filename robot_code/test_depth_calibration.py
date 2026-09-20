"""Shared camera-distance calibration regression; no GPU or motor access."""
from dataclasses import replace
import json
from pathlib import Path
import time

import numpy as np

from person_follow import front_approach_allowed, scale_tracking, select_people
from rgb_obstacles import Calibration, _observation_from_depth
from robot_steering import front_approach


def main():
    calibration = Calibration(**json.loads(Path(__file__).with_name('deberta-camera-calibration.json').read_text()))
    assert calibration.depth_scale == 1.75
    now = time.monotonic()
    # Saved scene's central obstacle estimates were 0.37-0.40 m before correction.
    depth = np.full((24, 32), .39, dtype=np.float32)
    raw = _observation_from_depth(depth, now, replace(calibration, depth_scale=1.))
    corrected = _observation_from_depth(depth, now, calibration)
    assert not raw.check(.35, 0, now=now)['safe']
    assert corrected.check(.35, 0, now=now)['safe']
    detected = select_people([[12, 1, 20, 22]], [.8], [1], depth)
    previous = scale_tracking(detected, 1.75)
    current = scale_tracking(select_people([[12, 1, 20, 22]], [.8], [1], depth * calibration.depth_scale), 1.)
    assert abs(previous['people'][0]['range_m'] - current['people'][0]['range_m']) < 1e-6
    assert front_approach_allowed(current, corrected, now)
    near = _observation_from_depth(np.full_like(depth, .15), now, calibration)
    assert not front_approach_allowed(current, near, now)
    assert not front_approach_allowed(current, corrected, now + 1)
    bad = _observation_from_depth(np.full_like(depth, np.nan), now, calibration)
    assert not front_approach_allowed(current, bad, now)
    result = dict(direction='straight', front_approach_clear=True)
    sensor = dict(connected=True, distance_cm=96.9, distance_age_ms=10,
                  distance_blocked=False, stop_distance_cm=50)
    assert front_approach(result, sensor)['direction'] == 'straight'
    for cm in (50., 49., 20.):
        assert front_approach(result, dict(sensor, distance_cm=cm, distance_blocked=True))['direction'] == 'stop'
    assert front_approach(result, dict(sensor, distance_age_ms=201))['direction'] == 'stop'
    assert front_approach(result, dict(sensor, distance_cm=None, distance_blocked=True))['direction'] == 'stop'
    print('PASS: consistent camera range, unchanged person distance, close/stale/invalid camera and 50 cm sensor stops')


if __name__ == '__main__':
    main()
