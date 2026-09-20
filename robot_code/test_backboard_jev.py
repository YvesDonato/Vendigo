"""Offline Backboard contract and robot constraint checks; never commands motors."""

from copy import deepcopy
from concurrent.futures import Future
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import numpy as np

from backboard_jev import BackboardJev, BackboardSteering, DIRECTIONS, ENDPOINT, NoRedirect
from person_follow import guarded_motion_options, validate_motion_options


def main():
    tracking = {"people": [{"box": [.4, .1, .6, .9], "score": .8, "range_m": 1.5}], "target": 0}
    observation = dict(direction="straight", reason="Camera route", source="vlm", latency_s=.1,
                       tracking=tracking, motion_options=list(DIRECTIONS))
    reply = {"status": "COMPLETED", "model_provider": "typesafe", "system_one": {
        "model": "jev-1.13.0", "answers": {"direction": {"type": "choice", "choice": "straight",
        "probabilities": {d: float(d == "straight") for d in DIRECTIONS}}}}}
    clock = [10.]

    class FakeAPI:
        def __init__(self, value, delay=0, error=None):
            self.value, self.delay, self.error, self.requests = value, delay, error, []

        def open(self, request, timeout):
            self.requests.append(request)
            assert request.full_url == ENDPOINT and 0 < timeout <= .5
            payload = json.loads(request.data)
            self.payload = payload
            assert payload["llm_provider"] == "typesafe" and payload["model_name"] == "jev-latest"
            assert payload["stream"] is False and payload["memory"] == "off"
            assert payload["system_one"]["questions"]["direction"]["type"] == "choice"
            assert payload["system_one"]["state"]["follow_gap_m"] == .5
            assert "image" not in payload and "thread_id" not in payload
            assert request.get_header("X-api-key") == "test-secret"
            clock[0] += self.delay
            if self.error:
                raise self.error
            return BytesIO(json.dumps(self.value).encode())

    with TemporaryDirectory() as tmp, patch("backboard_jev.time.monotonic", side_effect=lambda: clock[0]):
        key_file = Path(tmp) / "key"
        key_file.write_text("test-secret\n")
        model = BackboardJev(key_file, .5)

        def evaluate(value=reply, source=observation, delay=0, error=None):
            clock[0] = 10.
            model.opener = FakeAPI(value, delay, error)
            result = model.decide(source, 10.5)
            assert result["source"] == "backboard_jev" and "test-secret" not in json.dumps(result)
            return result

        for direction in DIRECTIONS:
            value = deepcopy(reply)
            value["system_one"]["answers"]["direction"].update(
                choice=direction, probabilities={d: float(d == direction) for d in DIRECTIONS})
            assert evaluate(value)["direction"] == direction, "Use the actual Jev choice, not the local suggestion"
        for side in ("left", "right"):
            evaluate(source=dict(observation, direction=side, tracking={"people": [], "target": None},
                                 motion_options=["stop", side]))
            state = model.opener.payload["system_one"]["state"]
            assert state["phase"] == "SEARCH" and state["search_side"] == side and state["target"] is None
        evaluate(source=dict(observation, direction="stop", tracking={"people": [], "target": None},
                             motion_options=["stop"]))
        assert model.opener.payload["system_one"]["state"]["phase"] == "HOLD", "Missing target during the wait must not become search"
        evaluate()
        state = model.opener.payload["system_one"]["state"]
        assert state["phase"] == "FOLLOW" and state["target"]["horizontal_position"] == .5
        assert "tracking" not in state, "Only the selected target is sent; bystanders cannot change the choice"
        stopped = evaluate(source=dict(observation, motion_options=["stop"]))
        assert stopped["direction"] == "stop" and stopped["jev"]["choice"] == "straight", "Jev cannot override the loss wait or close-target/obstacle constraints"
        assert evaluate(delay=.51)["direction"] == "stop", "Late replies cannot renew an observation"
        for error in (TimeoutError("test-secret"), HTTPError(ENDPOINT, 401, "test-secret", {}, None),
                      HTTPError(ENDPOINT, 402, "test-secret", {}, None)):
            assert evaluate(error=error)["direction"] == "stop", "No heuristic fallback after API failure"
        invalid = [None, {}, dict(reply, model_provider="openai"), dict(reply, status="REQUIRES_ACTION")]
        for field, value in (("type", "text"), ("choice", "reverse"), ("choice", "left"),
                             ("probabilities", {d: float("nan") for d in DIRECTIONS}),
                             ("probabilities", {d: .8 for d in DIRECTIONS})):
            bad = deepcopy(reply)
            bad["system_one"]["answers"]["direction"][field] = value
            invalid.append(bad)
        bad = deepcopy(reply)
        bad["system_one"]["model"] = "another-model"
        invalid.append(bad)
        for value in invalid:
            assert evaluate(value)["direction"] == "stop", value
        for options in (None, [], ["reverse", "stop"], ["left"], ["stop", "stop"], [{}, "stop"]):
            assert evaluate(source=dict(observation, motion_options=options))["direction"] == "stop"
            assert not model.opener.requests, "Reject malformed camera constraints before any API request"
        model.opener = FakeAPI(reply)
        clock[0] = 10.
        assert model.decide(observation, 9.9)["direction"] == "stop" and not model.opener.requests
        try:
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.invalid")
        except ValueError:
            pass
        else:
            raise AssertionError("API-key-bearing requests must not redirect")

    calibration = SimpleNamespace(max_age=.5, rear=-.0875, front=.0875, half_width=.06, lateral_margin=.03)
    cloud = SimpleNamespace(calibration=calibration, timestamp=10., error=None,
                            points=np.empty((0, 2)), check=lambda *a, **kw: {"safe": True})
    moving = dict(direction="straight", reason="Target ahead")
    assert set(guarded_motion_options(moving, tracking, cloud, 10.1)) == set(DIRECTIONS)
    assert guarded_motion_options(dict(direction="stop"), tracking, cloud, 10.1) == ["stop"]
    assert guarded_motion_options(moving, tracking, cloud, 10.6) == ["stop"]
    assert guarded_motion_options(moving, tracking, cloud, 9.9) == ["stop"]
    cloud.check = lambda *a, **kw: {"safe": False}
    assert guarded_motion_options(moving, tracking, cloud, 10.1) == ["stop", "left", "right"]
    cloud.points = np.array([[.01, .01]])
    assert guarded_motion_options(moving, tracking, cloud, 10.1) == ["stop"]
    cloud.check = lambda *a, **kw: {"safe": True}
    cloud.points = np.empty((0, 2))
    assert guarded_motion_options(dict(direction="right"), {"target": None}, cloud, 10.1) == ["stop", "right"]
    cloud.error = "Failed estimate"
    assert guarded_motion_options(moving, tracking, cloud, 10.1) == ["stop"]
    validate_motion_options(["stop"])

    class PendingAPI:
        def __init__(self):
            self.jobs = []

        def submit(self, *args):
            future = Future()
            self.jobs.append((future, args))
            return future

    runner = BackboardSteering.__new__(BackboardSteering)
    runner.model = SimpleNamespace(gap=.5, decide=lambda *_: None)
    runner.executor = PendingAPI()
    runner.pending = runner.last = None
    runner.retry_at = 0.
    accepted = dict(observation, jev=dict(model="jev-1.13.0", choice="straight", probabilities={
        d: float(d == "straight") for d in DIRECTIONS}), latency_s=.9)
    with patch("backboard_jev.time.monotonic", side_effect=lambda: clock[0]):
        clock[0] = 100.
        assert runner.update(observation, 10, 100.)["direction"] == "stop"
        for frame in range(11, 14):
            clock[0] += .1
            assert runner.update(observation, frame, clock[0])["direction"] == "stop"
        assert len(runner.executor.jobs) == 1, "No request queue while Jev is pending"
        runner.executor.jobs[0][0].set_result(accepted)
        clock[0] = 100.9
        result = runner.update(observation, 14, 100.9)
        assert result["direction"] == "straight" and result["jev"]["frame_id"] == 10
        assert result["jev"]["observation_age_ms"] == 900 and result["tracking"] == tracking
        assert len(runner.executor.jobs) == 2
        clock[0] = 101.
        assert runner.update(dict(observation, direction="left"), 15, 101.)["direction"] == "stop", "Current target changes immediately veto old direction"
        assert runner.update(dict(observation, direction="stop", motion_options=["stop"]), 16, 101.)["direction"] == "stop", "Close/lost target or new obstacle stops immediately"
        assert runner.update(observation, 17, 101.)["direction"] == "straight"
        clock[0] = 102.
        assert runner.update(observation, 18, 102.)["direction"] == "stop", "Intent age starts at original capture, not API completion"
        runner.executor.jobs[1][0].set_result(dict(observation, direction="stop", reason="API failed"))
        clock[0] = 102.1
        assert runner.update(observation, 19, 102.1)["direction"] == "stop"
        clock[0] = 103.
        assert runner.update(observation, 20, 103.)["direction"] == "stop" and len(runner.executor.jobs) == 2
        clock[0] = 104.2
        assert runner.update(observation, 21, 104.2)["direction"] == "stop" and len(runner.executor.jobs) == 3
        assert runner.update(observation, 22, 103.)["direction"] == "stop", "A fresh intent cannot authorize stale perception"
    print("PASS: hosted Jev contract, asynchronous single request, fresh-frame vetoes, bounded intent age, API failures, credential redaction and no redirects; offline, no motors.")


if __name__ == "__main__":
    main()
