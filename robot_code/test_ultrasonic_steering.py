"""Run with the staged/installed iPlanner host on PYTHONPATH. No real motors."""

from types import SimpleNamespace
import threading
import time

from robot_steering import RobotSteering
from test_robot_steering import rejected, wait_for


def main(cutoff=50):
    relay = SimpleNamespace(condition=threading.Condition(), stopping=threading.Event(),
                            args=SimpleNamespace(max_frame_age=.5), generation=0, model_ready=True)
    def frame(direction="straight"):
        f = SimpleNamespace(id=1, generation=0, received=time.monotonic())
        with relay.condition:
            relay.latest = f
            relay.decision = (f, dict(direction=direction))
    frame()
    robot = RobotSteering(relay, "http://127.0.0.1", "a" * 64, speed=255, turn_speed=200, stop_distance_cm=cutoff)
    sensor = dict(distance_guard=True, distance_cm=cutoff + 1., distance_age_ms=20,
                  distance_blocked=False, stop_distance_cm=15)
    calls = []
    def request(path, fields=None):
        calls.append((path, fields))
        if path == "/stop-distance":
            sensor["stop_distance_cm"] = fields["cm"]
        if path == "/arm":
            return dict(session=42)
        return dict(ok=True, firmware="lordbot-jev-2", max_speed=255, **sensor)
    robot.request = request
    worker = threading.Thread(target=robot.run, daemon=True)
    worker.start()
    try:
        wait_for(lambda: robot.snapshot()["connected"])
        assert ("/stop-distance", {"cm": cutoff}) in calls
        assert not any(path == "/drive" for path, _ in calls), "Sensor setup must not start driving"
        frame()
        robot.action("arm")
        wait_for(lambda: robot.snapshot()["direction"] == "straight")
        assert any(path == "/drive" and fields["direction"] == "straight" and fields["speed"] == 255 for path, fields in calls)
        for change in (dict(distance_cm=float(cutoff), distance_blocked=True),
                       dict(distance_cm=None, distance_blocked=True),
                       dict(distance_cm=75., distance_age_ms=201, distance_blocked=True)):
            sensor.update(change)
            frame()
            wait_for(lambda: robot.snapshot()["direction"] == "stop")
            assert robot.snapshot()["enabled"], "Front sensor pause must not cancel following"
            sensor.update(distance_cm=cutoff + 1., distance_age_ms=20, distance_blocked=False)
            frame()
            wait_for(lambda: robot.snapshot()["direction"] == "straight")
        sensor.update(distance_cm=cutoff - 1., distance_blocked=True)
        for direction in ("left", "right"):
            frame(direction)
            wait_for(lambda: robot.snapshot()["direction"] == direction)
            assert any(path == "/drive" and fields["direction"] == direction and fields["speed"] == 200 for path, fields in calls)
        assert robot.snapshot()["distance_cm"] == cutoff - 1., "Front-only readings must not masquerade as side clearance"
        before_stop = len(calls)
        robot.action("stop")
        wait_for(lambda: any(path == "/stop" for path, _ in calls[before_stop:]))
        assert not robot.snapshot()["enabled"]
        for change in (dict(distance_guard=False), dict(distance_cm=float("nan")),
                       dict(distance_cm=True), dict(distance_age_ms=-1), dict(distance_age_ms=True),
                       dict(stop_distance_cm=cutoff - 1), dict(distance_blocked=False)):
            rejected(lambda: robot.update_distance(dict(sensor, **change)))
        for bad in (True, 0, 101, 50.5):
            rejected(lambda: RobotSteering(relay, robot.url, "a" * 64, stop_distance_cm=bad))
    finally:
        relay.stopping.set()
        robot.close()
        worker.join(timeout=2)
    assert not worker.is_alive()
    print(f"PASS: {cutoff} cm configuration, PWM 255 straight / 200 left and right, startup stopped, near/missing/stale forward pause, clear resume and strict telemetry")


if __name__ == "__main__":
    for cutoff in (25, 50):
        main(cutoff)
