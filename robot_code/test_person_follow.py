"""Person-following policy/protocol check; put iPlanner on PYTHONPATH. No robot/GPU."""

from copy import deepcopy
from collections import deque
import numpy as np

from person_follow import LOST_WAIT_SECONDS, PersonFollower, follow_decision, merge_feet, scale_tracking, select_people, validate_tracking


def rejected(action):
    try:
        action()
    except (ValueError, TypeError):
        return
    raise AssertionError("Malformed tracking data was accepted")


def main():
    assert LOST_WAIT_SECONDS == 2.0
    depth = np.full((100, 100), 4.)
    depth[10:90, 60:90] = 2.
    tracking = select_people([[10, 10, 40, 90], [60, 10, 90, 90], [40, 10, 60, 90]],
                             [.95, .85, .99], [1, 1, 2], depth)
    assert len(tracking["people"]) == 2 and tracking["people"][0]["range_m"] == 2
    assert follow_decision(tracking, 1.2)["direction"] == "right", "Follow nearest, not highest score"
    mirror = deepcopy(tracking)
    mirror["people"][0]["box"] = [.1, .1, .4, .9]
    assert follow_decision(mirror, 1.2)["direction"] == "left"
    centered = deepcopy(tracking)
    centered["people"][0]["box"] = [.35, .1, .65, .9]
    assert follow_decision(centered, 1.2)["direction"] == "straight"
    close = deepcopy(centered)
    close["people"][0]["range_m"] = 1.
    assert follow_decision(close, 1.2)["direction"] == "stop", "Never approach or reverse around a close person"
    fills_view = deepcopy(centered)
    fills_view["people"][0]["box"] = [.1, .1, .9, .9]
    assert follow_decision(fills_view, 1.2)["direction"] == "straight", "Box size alone must not stop a distant target"
    live_seated = dict(people=[dict(box=[.1363, .0203, .8381, .7105], score=.6576, range_m=1.8675)], target=0)
    assert follow_decision(live_seated, 1.)["direction"] == "straight", "Regression: the live 1.9 m seated person was falsely marked close"
    fills_view["people"][0]["range_m"] = .9
    assert follow_decision(fills_view, 1.)["direction"] == "stop", "Large nearby targets still respect the gap"
    feet = select_people([[42, 60, 58, 80]], [.35], [1], np.full((100, 100), 1.1), kind="feet")
    assert feet["people"][0]["kind"] == "feet"
    assert follow_decision(feet, 1.)["direction"] == "straight"
    assert "feet" in follow_decision(feet, 1.)["reason"].lower()
    feet["people"][0]["range_m"] = 1.
    assert follow_decision(feet, 1.)["direction"] == "stop", "One-metre gap applies to feet too"
    for kind in ("person", "feet"):
        for distance in (.24, .25, .26, .49):
            nearby = dict(people=[dict(box=[.4, .1, .6, .9], score=.8, range_m=distance, kind=kind)], target=0)
            decision = follow_decision(nearby, .25)
            assert decision["direction"] == ("straight" if distance > .25 else "stop")
            assert "gap 0.25 m" in decision["reason"], "Do not round the requested gap to 0.2 m"
    for bad_gap in (.249, 3.01, True, float("inf")):
        rejected(lambda: follow_decision(feet, bad_gap))
    measured = deepcopy(feet)
    measured["people"][0]["range_m"] = 1.5 / 1.75
    corrected = scale_tracking(measured, 1.75)
    assert abs(corrected["people"][0]["range_m"] - 1.5) < 1e-9
    assert follow_decision(corrected, 1.)["direction"] == "straight"
    assert follow_decision(measured, 1.)["direction"] == "stop", "Correction must not mutate source estimates"
    corrected["people"][0]["range_m"] = 1.
    assert follow_decision(corrected, 1.)["direction"] == "stop", "Retain the one-metre gap after calibration"
    for bad_scale in (0, float("nan"), 5.1):
        rejected(lambda: scale_tracking(measured, bad_scale))
    assert merge_feet(centered, feet) == centered, "Don't duplicate a detected person's own feet"
    combined = merge_feet(tracking, feet)
    assert combined["people"][0]["kind"] == "feet", "Near feet outrank a distant body elsewhere"
    assert len(combined["people"]) == 3
    assert not select_people([[42, 60, 58, 80]], [.249], [1], depth, kind="feet")["people"]
    rejected(lambda: select_people([[42, 60, 58, 80]], [.8], [1], depth, kind="shoe"))
    broken_feet = deepcopy(feet)
    broken_feet["people"][0]["score"] = .249
    rejected(lambda: validate_tracking(broken_feet))
    broken_feet["people"][0]["kind"] = "unknown"
    rejected(lambda: validate_tracking(broken_feet))
    lost = select_people([[10, 10, 40, 90]], [.59], [1], depth)
    assert lost == {"people": [], "target": None}
    assert follow_decision(lost, 1.2)["direction"] == "left"
    assert follow_decision(lost, 1.2, "right")["direction"] == "right", "Search toward last seen side"
    assert follow_decision(centered, 1.2)["direction"] == "straight", "Reacquisition resumes following"
    follower = PersonFollower.__new__(PersonFollower)
    follower.reset_target()
    follower.gap, follower.search_direction = 1.2, "left"
    follower.range_samples, follower.last_target_box = deque(maxlen=3), None
    follower.last_seen_at, follower.lost_since = None, None
    assert follower.choose_direction(lost, 99)["direction"] == "left", "No previous target must search"
    assert follower.choose_direction(live_seated, 99.1)["direction"] == "straight", "A found centred target must immediately replace searching with forward"
    assert follower.choose_direction(centered, 100)["direction"] == "straight"
    for now in (100.1, 100.4, 101.5, 102., 102.09):
        held = follower.choose_direction(lost, now)
        assert held["direction"] == "stop" and held["reason"].startswith("Person lost; waiting still")
    expired = follower.choose_direction(lost, 100.1 + LOST_WAIT_SECONDS)
    assert expired["direction"] == "left" and expired["reason"].startswith("Searching"), "Misses must not extend the wait"
    assert follower.choose_direction(lost, 104)["direction"] == "left", "Search must keep one direction while the target is absent"
    assert follower.choose_direction(tracking, 105)["direction"] == "right"
    assert follower.choose_direction(lost, 105.1)["direction"] == "stop", "Loss during a turn must stop turning"
    assert follower.choose_direction(mirror, 105.2)["direction"] == "left", "Reacquisition resumes following immediately"
    for now, box in ((105.3, [.34, .1, .64, .9]), (105.4, [.36, .1, .66, .9])):
        jitter = deepcopy(centered)
        jitter["people"][0]["box"] = box
        assert follower.choose_direction(jitter, now)["direction"] == "straight"
        assert follower.search_direction == "left", "Centre-line jitter must not reverse the remembered search side"
    assert follower.choose_direction(lost, 105.5)["direction"] == "stop"
    assert follower.choose_direction(lost, 107.49)["direction"] == "stop", "Reacquisition starts a new full wait on the next loss"
    assert follower.choose_direction(lost, 107.5)["direction"] == "left"
    follower.choose_direction(close, 110)
    assert follower.choose_direction(lost, 110.2)["direction"] == "stop", "Close-person stop cannot revive old motion"
    assert follower.choose_direction(lost, 109.9)["direction"] == "stop", "Clock rollback restarts a stationary wait"
    follower.gap = 1.
    follower.range_samples, follower.last_target_box = deque(maxlen=3), None
    noisy = deepcopy(feet)
    for now, distance in ((200., 1.2), (200.1, 1.15), (200.2, .95), (200.3, 1.1)):
        noisy["people"][0]["range_m"] = distance
        assert follower.choose_direction(noisy, now)["direction"] == "straight", "One isolated range dip must not stop following"
    noisy["people"][0]["range_m"] = .95
    assert follower.choose_direction(noisy, 200.4)["direction"] == "stop", "Repeated near readings retain the one-metre gap"
    noisy["people"][0]["range_m"] = 1.05
    assert follower.choose_direction(noisy, 200.5)["direction"] == "straight", "Resume without the old extra distance/time delay"
    noisy["people"][0]["range_m"] = .7
    assert follower.choose_direction(noisy, 200.6)["direction"] == "stop", "Clearly close targets stop immediately"
    assert len(follower.range_samples) == 1
    noisy["people"][0]["range_m"] = 1.2
    follower.choose_direction(noisy, 201.2)
    assert len(follower.range_samples) == 1, "Expired range samples must be discarded"
    changed = deepcopy(noisy)
    changed["people"][0]["box"] = [.75, .6, .95, .8]
    changed["people"][0]["range_m"] = .9
    assert follower.choose_direction(changed, 201.3)["direction"] == "stop", "A new nearer target must not inherit a distant target's range"
    follower.choose_direction(noisy, 201.4)
    follower.choose_direction(lost, 201.5)
    noisy["people"][0]["range_m"] = .9
    assert follower.choose_direction(noisy, 201.6)["direction"] == "stop", "Lost tracking clears distance history"
    follower.choose_direction(noisy, 201.55)
    assert len(follower.range_samples) == 1, "A backwards clock must reset distance history"
    noisy["people"][0]["range_m"] = 1.2
    follower.choose_direction(noisy, 202.1)
    follower.choose_direction(noisy, 202.45)
    follower.choose_direction(noisy, 202.55)
    assert len(follower.range_samples) == 2, "Every retained sample must remain within 0.4 seconds"
    rejected(lambda: follow_decision(lost, float("nan")))
    rejected(lambda: select_people([[0, 0, 10, 10]], [.9], [1], np.full((100, 100), np.nan)))
    rejected(lambda: select_people([[0, 0, 10, 10]], [.9, .8], [1], depth))
    for field, invalid in (("score", float("nan")), ("range_m", 0), ("box", [-1, 0, 1, 1])):
        broken = deepcopy(tracking)
        broken["people"][0][field] = invalid
        rejected(lambda: validate_tracking(broken))
    rejected(lambda: validate_tracking(dict(people=tracking["people"], target=len(tracking["people"]))))
    rejected(lambda: validate_tracking(dict(people=[], target=0)))
    rejected(lambda: validate_tracking(dict(people=tracking["people"], target=True)))

    follower = PersonFollower.__new__(PersonFollower)
    follower.reset_target()
    follower.gap, follower.search_direction = 1., "left"
    follower.range_samples, follower.last_target_box = deque(maxlen=3), None
    follower.last_seen_at, follower.lost_since, follower.locked_target = None, None, None
    person = dict(box=[.4, .1, .6, .9], score=.8, range_m=2.)
    bystander = dict(box=[.05, .1, .25, .9], score=.9, range_m=1.5)
    def step(people, now):
        candidates = dict(people=sorted(deepcopy(people), key=lambda p:p["range_m"]), target=0 if people else None)
        selected = follower.select_target(candidates, now)
        return selected, follower.choose_direction(selected, now)
    selected, decision = step([bystander, person], 300)
    assert selected["target"] == 1 and decision["direction"] == "straight", "Start with the centred person, not a closer bystander"
    person["box"] = [.52, .1, .72, .9]
    selected, decision = step([bystander, person], 300.1)
    assert selected["target"] == 1, "Keep the same target as it moves"
    intruder = dict(box=[.38, .1, .49, .9], score=.95, range_m=1.4)
    selected, decision = step([intruder, person], 300.2)
    assert selected["target"] == 1, "A more central, nearer person must not steal an established target"
    selected, decision = step([bystander], 300.3)
    assert selected["target"] is None and decision["direction"] == "stop", "Wait for the selected person even with a bystander visible"
    selected, decision = step([bystander], 302.29)
    assert selected["target"] is None and decision["direction"] == "stop"
    selected, decision = step([person, bystander], 302.295)
    assert selected["target"] == 1 and decision["direction"] != "stop", "Reacquire the same person before timeout"
    feet_of_person = dict(box=[.56, .81, .64, .94], score=.4, range_m=2., kind="feet")
    selected, decision = step([feet_of_person, bystander], 303.4)
    assert selected["target"] == 1, "Keep the target when the body is replaced by its feet"
    selected, decision = step([person, bystander], 303.5)
    assert selected["target"] == 1, "Feet can reacquire their body box"
    step([bystander], 304.)
    selected, decision = step([bystander], 306.)
    assert selected["target"] == 0 and decision["direction"] == "left", "Choose a new centred target only after the full wait expires"
    print("PASS: centred initial selection, retained target, body/feet association, 2-second stationary loss wait despite bystanders, stable search side, immediate forward for distant large boxes, calibrated gap, range smoothing and invalid input rejection")


if __name__ == "__main__":
    main()
