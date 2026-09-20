"""Run with the iPlanner source on PYTHONPATH; no GPU or robot needed."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import time

import numpy as np

from rgb_obstacles import Calibration, Observation, _observation_from_depth
from vlm_reasoner import DebertaCameraNavigation


def main():
    values = json.loads(Path(__file__).with_name("deberta-camera-calibration.json").read_text())
    calibration = Calibration(**values)
    assert calibration.camera_height == .09 and calibration.half_width * 2 == .12
    assert calibration.front - calibration.rear == .175

    # At 30 degrees down, the central ray at 10 cm has height 4 cm and
    # horizontal range 8.66 cm. Include the front-mounted optical offset.
    tilted = replace(calibration, camera_pitch_deg=30)
    depth = np.full((2, 2), 19.)
    depth[1, 1] = .1
    observation = _observation_from_depth(depth, 10, tilted)
    expected_x = .1 * np.cos(np.pi / 6) + calibration.camera_forward
    assert np.min(np.linalg.norm(observation.points - [expected_x, 0], axis=1)) < .015
    ranged = replace(calibration, min_range_fraction=.4)
    uncertain = Observation(np.array([[.75, 0.]]), 10, ranged)
    assert uncertain.check(.1, 0, now=10.1)["safe"], "Range intervals must start at the optical origin"
    assert not replace(uncertain, calibration=replace(ranged, camera_forward=0)).check(.1, 0, now=10.1)["safe"]

    for override in ({"camera_pitch_deg": 46}, {"camera_forward": float("nan")}):
        try:
            replace(calibration, **override)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid camera placement accepted")

    # Exercise RGB -> observation -> the training descriptor -> learned
    # choice, including veto of a learned choice blocked by its own evidence.
    rgb = np.zeros((24, 32, 3), dtype=np.uint8)
    rgb[:, :16] = 255
    points = np.empty((0, 2))
    descriptions = []
    adapter = DebertaCameraNavigation.__new__(DebertaCameraNavigation)
    def observe(pixels, timestamp):
        np.testing.assert_array_equal(pixels, rgb)
        return Observation(points, timestamp, calibration)
    def decide(description):
        descriptions.append(description)
        return dict(direction="straight", reason="Test trained choice")
    adapter.guard = SimpleNamespace(observe=observe)
    adapter.model = SimpleNamespace(decide=decide)
    assert adapter.decide(rgb, [])["direction"] == "straight"
    assert "Straight at 0.35 m/s: stopping envelope clear" in descriptions[-1]
    points = np.array([[.15, 0.]])
    assert adapter.decide(rgb, [])["direction"] == "stop"
    assert "stopping envelope blocked" in descriptions[-1]
    adapter.guard.observe = lambda _, __: Observation(points, time.monotonic() - 1, calibration)
    try:
        adapter.decide(rgb, [])
    except ValueError:
        pass
    else:
        raise AssertionError("Expired depth observation reached the model")
    print("PASS: measured dimensions, camera pitch/offset, depth range origin, trained descriptor, blocked-choice veto and stale rejection")


if __name__ == "__main__":
    main()
