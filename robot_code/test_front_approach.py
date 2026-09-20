"""Measured final approach checks; iPlanner on PYTHONPATH, no motors or GPU."""

from copy import deepcopy
from io import BytesIO
import json
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image

from camera_live import Relay
from person_follow import front_approach_allowed
from rgb_obstacles import Calibration, Observation
from robot_steering import RobotSteering, drive_intent, front_approach
from vlm_reasoner import Reasoner


def main(cutoff=50):
    # A shoe can be inside the forward steering band without its box crossing
    # the centre beam. Such commands still need the firmware's sonar clearance.
    offcentre = dict(direction='straight', reason='Following selected feet', front_approach_clear=False,
                     tracking=dict(people=[dict(box=[.53,.6,.64,.8],score=.8,range_m=1.5,kind='feet')],target=0))
    clear_sensor = dict(connected=True, distance_cm=75., distance_age_ms=20,
                        distance_blocked=False, stop_distance_cm=cutoff)
    assert front_approach(offcentre, clear_sensor) == offcentre
    for change in (dict(distance_cm=None), dict(distance_age_ms=201),
                   dict(distance_cm=cutoff, distance_blocked=True), dict(connected=False)):
        blocked = front_approach(offcentre, dict(clear_sensor, **change))
        assert blocked['direction']=='stop' and blocked['model_direction']=='straight'
        assert blocked['source']=='ultrasonic_guard'
    assert front_approach(dict(offcentre,direction='left'),dict(clear_sensor,distance_cm=None))['direction']=='left'
    tracking = dict(people=[dict(box=[.41, .1, .67, .9], score=.8, range_m=.47)], target=0)
    now = time.monotonic()
    clear = Observation(np.array([[2., 0.]]), now, Calibration())
    assert front_approach_allowed(tracking, clear, now)
    assert not front_approach_allowed(tracking, clear, now + 1)
    assert not front_approach_allowed(dict(people=[], target=None), clear, now)
    blocked = Observation(np.array([[.1, 0.]]), now, Calibration())
    assert not front_approach_allowed(tracking, blocked, now)
    side = deepcopy(tracking)
    side['people'][0]['box'] = [.7, .1, .9, .9]
    assert not front_approach_allowed(side, clear, now), 'Front range cannot authorize a side target'
    side['people'][0]['box'] = [.4, .1, .49, .9]
    assert not front_approach_allowed(side, clear, now), 'Target must overlap the front beam centre'

    camera = np.zeros((24, 32, 3), dtype=np.uint8)
    camera[:, :16, 0] = 255
    buf = BytesIO()
    Image.fromarray(camera).save(buf, format='JPEG')
    relay = Relay(SimpleNamespace(max_frame_age=.5))
    robot = RobotSteering(relay, 'http://127.0.0.1', 'a' * 64, stop_distance_cm=cutoff)
    relay.steering = robot
    robot.connected = True
    result = dict(direction='stop', reason='Camera estimates the person at 0.47 m',
                  source='vlm', latency_s=.1, tracking=tracking, front_approach_clear=True)
    sensor = dict(distance_guard=True, distance_cm=114., distance_age_ms=10,
                  distance_blocked=False, stop_distance_cm=cutoff)

    # Actual host control and UI must agree, across repeated model holds.
    for cm in (114., 75., cutoff + 1., float(cutoff), cutoff - 1., cutoff + 1.):
        sensor.update(distance_cm=cm, distance_blocked=cm <= cutoff)
        robot.update_distance(sensor)
        frame = relay.record_frame(buf.getvalue())
        relay.model_ready = True
        relay.publish_decision(frame, result)
        expected = 'straight' if cm > cutoff else 'stop'
        assert drive_intent(relay, time.monotonic())[0] == expected
        shown = relay.snapshot()['decision']
        assert shown['direction'] == expected and shown['model_direction'] == 'stop'
        assert shown['source'] == 'ultrasonic_approach'
    for change in (dict(distance_cm=None), dict(distance_age_ms=201)):
        bad = dict(sensor, **change, distance_blocked=True)
        robot.update_distance(bad)
        assert drive_intent(relay, time.monotonic())[0] == 'stop'
    robot.update_distance(sensor)
    assert front_approach(dict(result, front_approach_clear=False), robot.snapshot()) == dict(result, front_approach_clear=False)
    assert front_approach(result, None) == result
    # A clear sensor cannot revive expired camera evidence or an explicit Stop.
    relay.record_frame(buf.getvalue())
    relay.publish_decision(frame, result)
    try:
        drive_intent(relay, frame.received + .6)
    except ValueError:
        pass
    else:
        raise AssertionError('Expired camera decision authorized movement')
    robot.action('stop')
    assert not robot.enabled

    # Exercise the real IPC decoder, including strict clearance validation.
    worker = '''import json,sys
print(json.dumps({'ready':True,'metadata':{'name':'test','backend':'person_follow','front_approach_version':1}}),flush=True)
for n,line in enumerate(sys.stdin):
 json.loads(line)
 print(json.dumps({'ok':True,'decision':{'direction':'stop','reason':'Camera estimate'},'latency_s':.1,'tracking':{'people':[],'target':None},'front_approach_clear':True if n==0 else 'yes'}),flush=True)
'''
    reasoner = Reasoner(None, None, command=[sys.executable, '-u', '-c', worker])
    try:
        assert reasoner.submit(camera, []).result(timeout=3)['front_approach_clear'] is True
        try:
            reasoner.submit(camera, []).result(timeout=3)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed approach clearance accepted')
    finally:
        reasoner.close()
    print(f'PASS: measured approach to {cutoff} cm, clear resume, obstacle/alignment/loss/freshness guards, UI and IPC')


if __name__ == '__main__':
    for cutoff in (25, 50):
        main(cutoff)
