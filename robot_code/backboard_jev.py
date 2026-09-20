"""Hosted TypeSafe Jev decisions over camera-derived observations; no raw images."""

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from person_follow import validate_motion_options, validate_tracking

ENDPOINT = "https://app.backboard.io/api/threads/messages"
DIRECTIONS = ("straight", "left", "right", "stop")
INTENT_MAX_AGE = 2.0
QUESTION = {
    "type": "choice",
    "instructions": (
        "Choose the robot movement for the explicit phase in state. "
        "HOLD: stop for the distance gap, waiting period or blocked route. "
        "SEARCH: the stationary wait has ended (or no target has been acquired yet); "
        "rotate toward search_side to find a person. "
        "FOLLOW: approach the selected target beyond follow_gap_m, keeping it centred. "
        "Turn left if horizontal_position < 0.38, right if > 0.62, otherwise straight. "
        "Stop at or inside the gap. Only select an allowed_direction. "
        "Stop if the required movement is blocked. All observations are camera estimates."
    ),
    "criteria": {
        "straight": "FOLLOW a centred target beyond the gap when straight is allowed.",
        "left": "SEARCH left when search_side is left, or FOLLOW a target on the left; left must be allowed.",
        "right": "SEARCH right when search_side is right, or FOLLOW a target on the right; right must be allowed.",
        "stop": "HOLD, a target inside the gap, or the required movement is blocked.",
    },
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Backboard redirect refused")


class BackboardJev:
    def __init__(self, key_file, gap):
        key = key_file.read_text().strip()
        if not key or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("Invalid Backboard API key file")
        if type(gap) not in (int, float) or not math.isfinite(gap) or not .5 <= gap <= 3:
            raise ValueError("Invalid Backboard following gap")
        self.key, self.gap = key, gap
        self.opener = build_opener(NoRedirect())

    def decide(self, observation, deadline):
        """Bound the hosted intent lifetime; fresh local perception must authorize motion."""
        started = time.monotonic()
        result = dict(observation, direction="stop", source="backboard_jev")
        try:
            tracking = validate_tracking(observation.get("tracking"))
            allowed = validate_motion_options(observation.get("motion_options"))
            index = tracking["target"]
            person = tracking["people"][index] if index is not None else None
            phase = "HOLD" if observation["direction"] == "stop" else "FOLLOW" if person else "SEARCH"
            state = {"phase": phase, "follow_gap_m": self.gap, "allowed_directions": allowed,
                     "search_side": observation["direction"] if phase == "SEARCH" else None,
                     "target": None if person is None else {
                         "kind": person.get("kind", "person"), "range_m": person["range_m"],
                         "horizontal_position": (person["box"][0] + person["box"][2]) / 2}}
            if not math.isfinite(deadline) or started >= deadline:
                raise TimeoutError("Camera decision expired before Jev request")
            payload = {
                "content": f"The robot is in {phase} phase. Choose its next movement from the current state.",
                "llm_provider": "typesafe", "model_name": "jev-latest", "stream": False,
                "memory": "off",
                # ponytail: independent observations avoid stale conversational state;
                # add explicit mission memory only if the task needs it.
                "system_one": {
                    "questions": {"direction": QUESTION},
                    "state": state,
                },
            }
            request = Request(ENDPOINT, json.dumps(payload, allow_nan=False).encode(), headers={
                "X-API-Key": self.key, "Content-Type": "application/json", "Accept": "application/json",
            })
            with self.opener.open(request, timeout=min(2., deadline - started)) as response:
                data = response.read(65537)
            if len(data) > 65536:
                raise ValueError("Backboard response exceeds 64 KiB")
            if time.monotonic() >= deadline:
                raise TimeoutError("Jev reply arrived after the camera deadline")
            reply = json.loads(data)
            if not isinstance(reply, dict) or reply.get("status") != "COMPLETED" or reply.get("model_provider") != "typesafe":
                raise ValueError("Expected a completed TypeSafe Jev response")
            system = reply.get("system_one")
            if not isinstance(system, dict):
                raise ValueError("Missing Jev System One result")
            model = system.get("model")
            if not isinstance(model, str) or not re.fullmatch(r"jev-[A-Za-z0-9_.-]{1,64}", model):
                raise ValueError("Invalid resolved Jev model")
            answers = system.get("answers")
            answer = answers.get("direction") if isinstance(answers, dict) else None
            if not isinstance(answer, dict) or answer.get("type") != "choice":
                raise ValueError("Missing typed Jev direction")
            choice, probabilities = answer.get("choice"), answer.get("probabilities")
            if (not isinstance(choice, str) or choice not in DIRECTIONS
                    or not isinstance(probabilities, dict) or set(probabilities) != set(DIRECTIONS)
                    or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                           for p in probabilities.values())
                    or not math.isclose(sum(probabilities.values()), 1., abs_tol=1e-4)
                    or probabilities[choice] != max(probabilities.values())):
                raise ValueError("Invalid Jev direction probabilities")
            result["jev"] = {"model": model, "choice": choice, "probabilities": probabilities}
            if choice not in allowed:
                result["reason"] = f"Jev chose {choice}; current camera constraints require a stop."
            else:
                result.update(direction=choice, reason=f"TypeSafe {model}: {choice} (estimated gap {self.gap:.1f} m; camera-derived observations).")
        except HTTPError as error:
            result["reason"] = f"Backboard HTTP {error.code}; movement stopped. Check API key or account credits."
        except (OSError, URLError, ValueError, TypeError) as error:
            # Do not expose response bodies, request headers or credentials in the viewer.
            result["reason"] = f"Backboard Jev unavailable or invalid ({type(error).__name__}); movement stopped."
        result["latency_s"] = observation.get("latency_s", 0.) + time.monotonic() - started
        return result


class BackboardSteering:
    """One hosted request at a time, checked against every fresh camera decision."""

    def __init__(self, model):
        self.model = model
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backboard-jev")
        self.pending = self.last = None
        self.retry_at = 0.

    def update(self, observation, frame_id, captured):
        now = time.monotonic()
        result = dict(observation, direction="stop", source="backboard_jev")
        if self.pending and self.pending[0].done():
            future, original_id, original_time = self.pending
            reply = future.result()
            self.last = reply, original_id, original_time
            self.pending = None
            self.retry_at = now if reply.get("jev") else now + 2.
        if not 0 <= now - captured < .5:
            result["reason"] = "Current camera observation expired; movement stopped."
            return result
        validate_tracking(observation.get("tracking"))
        allowed = validate_motion_options(observation.get("motion_options"))
        if self.pending is None and now >= self.retry_at:
            self.pending = (self.executor.submit(self.model.decide, observation, captured + INTENT_MAX_AGE), frame_id, captured)
        if self.last is None:
            result["reason"] = "Waiting for TypeSafe Jev; movement stopped."
            return result
        reply, original_id, original_time = self.last
        age = now - original_time
        if reply.get("jev"):
            result["jev"] = dict(reply["jev"], frame_id=original_id,
                                 observation_age_ms=round(age * 1000),
                                 round_trip_ms=round(reply["latency_s"] * 1000))
        if not 0 <= age < INTENT_MAX_AGE:
            result["reason"] = "Jev intent expired; waiting for a new decision."
        elif not reply.get("jev"):
            result["reason"] = reply["reason"]
        elif observation["direction"] == "stop":
            result["reason"] = observation["reason"]
        elif reply["direction"] == "stop":
            result["reason"] = reply["reason"]
        elif reply["direction"] not in allowed or reply["direction"] != observation["direction"]:
            # A hosted result cannot keep turning after the target has centred,
            # approach a missing target, or bypass a newly blocked route.
            result["reason"] = "Jev direction no longer fits the current target or route; updating."
        else:
            result.update(direction=reply["direction"], reason=(
                f"TypeSafe {reply['jev']['model']}: {reply['direction']}; checked against the current camera "
                f"(Jev observation {age:.1f} s old; estimated gap {self.model.gap:.1f} m)."))
        return result

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
