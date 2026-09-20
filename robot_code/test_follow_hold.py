"""Bounded continuation while visible bystanders do not match the target; no motors."""

from io import BytesIO
import threading
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image

from camera_live import Relay
from person_follow import scene_motion_options
from rgb_obstacles import Calibration, Observation
from robot_steering import FOLLOW_HOLD_SECONDS, RobotSteering, WaitingForLeaseBudget, drive_intent, following_intent
from test_robot_steering import wait_for


def main():
    now = time.monotonic()
    scene = Observation(np.array([[2., 0.]]), now, Calibration())
    assert scene_motion_options(scene, now) == ['stop', 'straight', 'left', 'right']
    assert scene_motion_options(scene, now + 1) == ['stop']
    assert scene_motion_options(Observation(np.array([[.1, 0.]]), now, Calibration()), now) == ['stop']
    missing = dict(direction='stop', reason='Target lost', source='vlm', latency_s=.1,
                   tracking=dict(people=[dict(box=[.1,.2,.3,.9],score=.8,range_m=1.)], target=None),
                   clear_motion_options=['stop','straight','left','right'])
    sensor = dict(enabled=True, connected=True, distance_cm=75., distance_age_ms=20,
                  distance_blocked=False, stop_distance_cm=50, follow_direction='straight', follow_age_s=.5)
    for direction in ('straight','left','right'):
        expected = 'straight' if direction == 'straight' else 'stop'
        assert following_intent(missing, dict(sensor, follow_direction=direction))['direction'] == expected
    for change in (dict(follow_age_s=FOLLOW_HOLD_SECONDS), dict(follow_age_s=-1),
                   dict(enabled=False), dict(distance_cm=50.), dict(distance_cm=None),
                   dict(distance_age_ms=201), dict(distance_blocked=True), dict(connected=False)):
        assert following_intent(missing, dict(sensor, **change))['direction'] == 'stop'
    assert following_intent(dict(missing, clear_motion_options=['stop']), sensor)['direction'] == 'stop'

    rgb = np.zeros((24, 32, 3), dtype=np.uint8)
    rgb[:, :16, 0] = 255
    b = BytesIO(); Image.fromarray(rgb).save(b, format='JPEG')
    relay = Relay(SimpleNamespace(max_frame_age=.5))
    robot = RobotSteering(relay, 'http://127.0.0.1', 'a'*64, speed=255, turn_speed=255, stop_distance_cm=50)
    relay.steering = robot
    seen = dict(missing, direction='straight', reason='Person ahead',
                tracking=dict(people=[dict(box=[.4,.2,.6,.9],score=.8,range_m=1.)],target=0))
    def frame(result, age=0):
        f = relay.record_frame(b.getvalue(), received=time.monotonic()-age)
        relay.model_ready = True
        relay.publish_decision(f,result)
        return f
    def request(path, fields=None):
        calls.append((path, fields))
        if path == '/arm': return dict(session=42)
        return dict(ok=True, firmware='lordbot-jev-2', max_speed=255, distance_guard=True,
                    distance_cm=75., distance_age_ms=20, distance_blocked=False, stop_distance_cm=50)
    calls=[]
    robot.request=request
    frame(seen)
    worker=threading.Thread(target=robot.run,daemon=True);worker.start()
    try:
        wait_for(lambda:robot.snapshot()['connected'])
        frame(seen);robot.action('arm')
        wait_for(lambda:robot.snapshot()['follow_direction']=='straight')
        with robot.lock: remembered=robot.follow_seen
        until=remembered+.7
        while time.monotonic()<until:
            frame(missing)
            assert robot.snapshot()['enabled']
            time.sleep(.025)
        assert robot.snapshot()['direction']=='straight', 'A short detection loss must retain forward movement'
        assert relay.snapshot()['decision']['source']=='follow_hold'
        with robot.lock: assert robot.follow_seen==remembered, 'Missing frames must never extend the hold'
        until=remembered+1.2
        while time.monotonic()<until:
            frame(missing);time.sleep(.025)
        wait_for(lambda:robot.snapshot()['direction']=='stop')
        assert robot.snapshot()['follow_direction'] is None
        frame(seen);wait_for(lambda:robot.snapshot()['direction']=='straight')
        # Near-expiry evidence must not inject zero PWM while a lease is valid.
        marker=len(calls)
        frame(seen,age=.32)
        wait_for(lambda:robot.snapshot()['message'].startswith('Waiting for a fresh decision'))
        assert not any(p=='/drive' and f['speed']==0 for p,f in calls[marker:])
        try: drive_intent(relay,time.monotonic())
        except WaitingForLeaseBudget: pass
        else: raise AssertionError('Old evidence renewed movement')
        # A new stop wins even when the movement renewal budget is too short.
        frame(dict(missing,clear_motion_options=['stop']),age=.32)
        assert drive_intent(relay,time.monotonic())[0]=='stop'
        wait_for(lambda:robot.snapshot()['direction']=='stop')
        frame(seen);wait_for(lambda:robot.snapshot()['follow_direction']=='straight')
        robot.action('stop')
        assert robot.snapshot()['follow_direction'] is None
        marker=len(calls)
        frame(missing);time.sleep(.1)
        assert not any(p=='/drive' and f['speed']>0 for p,f in calls[marker:]), 'Stop must prevent memory-driven restart'
        relay.camera_lost('test')
        try: drive_intent(relay,time.monotonic())
        except ValueError: pass
        else: raise AssertionError('Camera loss allowed motion')
    finally:
        relay.close();worker.join(timeout=2)
    assert not worker.is_alive()
    print('PASS: forward-only 1 s hold, no lost-turn continuation, fixed expiry, clearance/range guards, immediate Stop and camera-loss stop')


if __name__=='__main__':main()
