"""CPU-only checks for the fine-tuning data, policy constraints and launch wiring."""

from types import SimpleNamespace
from contextlib import nullcontext
from itertools import permutations
import json
import numpy as np

from camera_live import remote_command
from openjev_follow import DIRECTIONS, RULES, OpenJevFollower, follow_state, prompts
from train_openjev_follow import dataset, teacher


def main():
    tracking = dict(people=[dict(box=[.4, .5, .6, .9], range_m=1.2, score=.8, kind="feet")], target=0)
    local = dict(direction="straight", reason="Following")
    state = follow_state(tracking, list(DIRECTIONS), local, .5)
    assert state["target"]["x"] == .5 and teacher(state) == "straight"
    for allowed in (list(DIRECTIONS), ["straight", "left", "stop"], ["left", "stop"]):
        original = dict(state, permitted=allowed)
        for order in permutations(allowed):
            changed = dict(state, permitted=list(order))
            assert prompts(changed) == prompts(original), 'Runtime permission order must match training features'
            assert changed['permitted'] == list(order), 'Prompt normalization must not mutate permission lists'
    state["target"]["range_m"] = .5
    assert teacher(state) == "stop"
    state["target"]["range_m"] = .501
    assert teacher(state) == "straight"
    for x, expected in ((.379, "left"), (.38, "straight"), (.62, "straight"), (.621, "right")):
        state["target"]["x"] = x
        assert teacher(state) == expected
    state["permitted"] = ["stop", "straight"]
    assert teacher(state) == "stop", "Blocked turns must stop, not substitute another move"
    for direction in ("left", "right", "stop"):
        state = follow_state(dict(people=[], target=None), ["stop"] if direction == "stop" else ["stop", direction],
                             dict(direction=direction), .5)
        assert teacher(state) == direction
    follower = OpenJevFollower.__new__(OpenJevFollower)
    stopped = dict(direction="stop", reason="Lost target; waiting still for 2 seconds")
    assert follower.decide(tracking, ["stop"], stopped, .5)["direction"] == "stop", "Guards must stop without model inference"
    follower.torch = SimpleNamespace(inference_mode=nullcontext, isfinite=np.isfinite)
    follower.head = None
    follower.features = lambda _: (None, np.array([0., 1., 0., 0.]))
    assert follower.decide(tracking, list(DIRECTIONS), local, .5)["direction"] == "stop", "A stale/wrong turn cannot override the centred target"
    follower.features = lambda _: (None, np.array([1., 0., 0., 0.]))
    assert follower.decide(tracking, list(DIRECTIONS), local, .5)["direction"] == "straight"
    assert follower.decide(tracking, ["stop", "left"], local, .5)["direction"] == "stop", "The model cannot override a blocked forward route"
    follower.turns_only = True
    calls = []
    def features(_):
        calls.append(True)
        return None, np.array([0., 1., 0., 0.])
    follower.features = features
    assert follower.decide(tracking, list(DIRECTIONS), local, .5)["direction"] == "straight"
    assert not calls, "Hybrid forward must skip OpenJEV entirely"
    assert follower.decide(tracking, ["stop", "left"], local, .5)["direction"] == "stop"
    assert follower.decide(tracking, ["stop"], stopped, .5)["direction"] == "stop"
    assert not calls, "A stop guard must not become a model turn"
    left = dict(direction="left", reason="Target on left")
    assert follower.decide(tracking, list(DIRECTIONS), left, .5)["direction"] == "left"
    assert calls, "Hybrid turns must use the actual model path"
    follower.features = lambda _: (None, np.array([1., 0., 0., 0.]))
    assert follower.decide(tracking, list(DIRECTIONS), left, .5)["direction"] == "stop", "OpenJEV cannot request hybrid forward"
    follower.features = lambda _: (None, np.array([0., 0., 1., 0.]))
    assert follower.decide(tracking, list(DIRECTIONS), dict(direction="right", reason="Target right"), .5)["direction"] == "right"
    splits = dataset()
    assert len(splits["test"]) == 200
    for rows in splits.values():
        assert all(teacher(row["state"]) == row["label"] for row in rows)
        assert all(len(prompts(row["state"])) == 4 for row in rows)
        for row in rows:
            # Preserve the exact strings used by the already-trained head,
            # including its different HOLD/SEARCH permission order.
            premise = RULES + '\nState: ' + json.dumps(row['state'], sort_keys=True, allow_nan=False)
            expected = [f'Premise: {premise}\nHypothesis: The next robot movement should be {d}.' for d in DIRECTIONS]
            assert prompts(row['state']) == expected
    args = SimpleNamespace(remote_dir="/experiment", deberta_calibration="/calibration.json", follow_person=True,
                           follow_gap=.5, follow_distance_scale=1.75, min_route_entailment=None, ssh_host="A100",
                           openjev_follow_model="/models/openjev", openjev_follow_head="/experiment/head.pt")
    command = remote_command(args)[-1]
    assert "--openjev-follow-model /models/openjev" in command and "--openjev-follow-head /experiment/head.pt" in command
    assert "--openjev-turns-only" not in command
    args.openjev_turns_only = True
    assert "--openjev-turns-only" in remote_command(args)[-1]
    print("PASS: gap/centering boundaries, loss/search states, obstacle veto, disjoint synthetic splits and OpenJEV launch wiring")


if __name__ == "__main__":
    main()
