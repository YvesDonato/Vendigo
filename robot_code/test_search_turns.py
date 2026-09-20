"""Bounded two-turn search and fresh clear-path handoff; synthetic motors only."""

import time
import sys
import numpy as np

from person_follow import clearest_direction
from rgb_obstacles import Calibration, Observation
from robot_steering import SEARCH_SETTLE_SECONDS, TURN_SETTLE_SECONDS, following_intent
from test_robot_steering import wait_for
from test_smooth_follow import fake_robot, movement
from vlm_reasoner import Reasoner


def protocol_checks():
    worker = '''import json,sys
print(json.dumps({'ready':True,'metadata':{'name':'test','backend':'person_follow','clear_motion_options_version':1,'clear_path_direction_version':1}}),flush=True)
for n,line in enumerate(sys.stdin):
 json.loads(line)
 print(json.dumps({'ok':True,'decision':{'direction':'left','reason':'Search'},'latency_s':.1,'tracking':{'people':[],'target':None},'clear_motion_options':['stop','straight'],'clear_path_direction':'straight' if n==0 else 'right'}),flush=True)
'''
    reasoner = Reasoner(None, None, command=[sys.executable, '-u', '-c', worker])
    try:
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        frame[:, :16, 0] = 255
        assert reasoner.submit(frame, []).result(timeout=3)['clear_path_direction'] == 'straight'
        try: reasoner.submit(frame, []).result(timeout=3)
        except ValueError: pass
        else: raise AssertionError('An unpermitted clear-path direction crossed IPC')
    finally:
        reasoner.close()
    print('PASS: clear-path IPC accepts only currently permitted directions')


def search_pause_checks():
    assert SEARCH_SETTLE_SECONDS == .005 and TURN_SETTLE_SECONDS == .02
    for searching in (False, True):
        with fake_robot(search_rotation_seconds=.4) as (relay, robot, state, calls, publish):
            publish('right', target=not searching); robot.action('arm')
            wait_for(lambda: robot.snapshot()['turn_phase'] == 'observing')
            first = movement(calls)[0]
            confirmed = next(t for t, p, _ in calls if p == '/status' and t > first[0])
            # A pre-settle image cannot restart even the faster search pulse.
            publish('right', received=confirmed + .002, target=not searching)
            time.sleep(.04)
            assert len(movement(calls)) == 1
            # An image after 10 ms qualifies only for a search, not tracking a person.
            publish('right', received=confirmed + .010, target=not searching)
            if searching:
                wait_for(lambda: len(movement(calls)) == 2)
            else:
                time.sleep(.04)
                assert len(movement(calls)) == 1, 'Following used the shorter search pause'
                publish('right')
                wait_for(lambda: len(movement(calls)) == 2)
            robot.action('stop')
    print('PASS: search waits 5 ms, following waits 20 ms; both require an analyzed post-stop frame')


def main():
    now = time.monotonic()
    def scene(points):
        return Observation(np.array(points, dtype=float).reshape(-1, 2), now, Calibration())
    assert clearest_direction(scene([[3, 0]]), now) == 'left'
    assert clearest_direction(scene([[4, 0], [3, 2], [3, -2]]), now) == 'straight'
    assert clearest_direction(scene([[.7, 0], [1, 1]]), now) == 'right'
    assert clearest_direction(scene([[.1, 0]]), now) == 'stop'
    assert clearest_direction(scene([]), now + 1) == 'stop'

    lost = dict(direction='right', reason='Search', tracking=dict(people=[], target=None),
                clear_motion_options=['stop', 'straight', 'left', 'right'], clear_path_direction='straight')
    sensor = dict(enabled=True, connected=True, distance_cm=80., distance_age_ms=10,
                  distance_blocked=False, stop_distance_cm=25, search_remaining_s=1.,
                  search_rotation_seconds=3.184, search_direction='left')
    assert following_intent(lost, sensor)['direction'] == 'left', 'Search side flipped'
    complete = dict(sensor, search_remaining_s=0.)
    assert following_intent(lost, complete)['direction'] == 'straight'
    assert following_intent(dict(lost, clear_path_direction='right'), complete)['direction'] == 'right'
    assert following_intent(lost, dict(sensor, enabled=False))['direction'] == 'right'
    for change in (dict(distance_cm=25.), dict(distance_cm=None), dict(distance_age_ms=201),
                   dict(distance_blocked=True), dict(connected=False), dict(stop_distance_cm=None)):
        assert following_intent(lost, dict(complete, **change))['direction'] == 'stop'
    assert following_intent(dict(lost, clear_motion_options=['stop']), complete)['direction'] == 'stop'

    with fake_robot(search_rotation_seconds=.4) as (relay, robot, state, calls, publish):
        def feed(seconds, direction='right', target=False):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                publish(direction, target=target); time.sleep(.02)
        publish('straight'); robot.action('arm')
        wait_for(lambda: robot.snapshot()['direction'] == 'straight')
        assert robot.snapshot()['search_remaining_s'] == .8
        marker = len(calls)
        feed(2.)
        turns = [c for c in movement(calls[marker:]) if c[2]['direction'] in ('left', 'right')]
        charged = sum(c[2]['lease_ms'] for c in turns)
        assert 720 <= charged <= 800, charged
        assert {c[2]['direction'] for c in turns} == {'right'}
        assert robot.snapshot()['search_remaining_s'] == 0
        assert relay.snapshot()['decision']['source'] == 'clear_path'
        assert robot.snapshot()['direction'] == 'straight'
        # The final budgeted pulse must execute before the post-stop image handoff.
        final = turns[-1]
        stopped = next(t for t, p, _ in calls if p == '/stop' and t > final[0])
        assert stopped - final[0] >= final[2]['lease_ms']/1000 - .02
        marker = len(calls)
        feed(.3)
        assert all(f['direction'] == 'straight' for _, _, f in movement(calls[marker:]))
        assert robot.snapshot()['search_remaining_s'] == 0, 'Empty frames restarted search'
        for _ in range(10): relay.snapshot()
        assert robot.snapshot()['search_remaining_s'] == 0, 'UI polling restarted search'
        state['distance_cm'] = 25.
        feed(.15)
        assert robot.snapshot()['direction'] == 'stop'
        state['distance_cm'] = 80.
        feed(.2)
        assert robot.snapshot()['direction'] == 'straight'
        assert robot.snapshot()['search_remaining_s'] == 0
        # A fresh person ends clear-path travel and resets the next loss budget.
        feed(.15, 'straight', True)
        assert robot.snapshot()['search_remaining_s'] == .8
        feed(.1)
        assert robot.snapshot()['search_remaining_s'] < .8
        feed(.35, 'straight', True)
        assert robot.snapshot()['search_remaining_s'] == .8
        assert robot.snapshot()['direction'] == 'straight'
        robot.action('stop'); time.sleep(.1)
        marker = len(calls); feed(.15)
        assert not movement(calls[marker:]), 'Stop allowed search restart'

    # An uncertain drive acknowledgement consumes budget rather than repeating it.
    with fake_robot(search_rotation_seconds=.2) as (relay, robot, state, calls, publish):
        publish('right', target=False); state['drive_error'] = True; robot.action('arm')
        until = time.monotonic() + 1.5
        while time.monotonic() < until:
            publish('right', target=False); time.sleep(.02)
        charged = sum(f['lease_ms'] for _, _, f in movement(calls) if f['direction'] == 'right')
        assert 320 <= charged <= 400, charged
        assert robot.snapshot()['search_remaining_s'] == 0
        relay.camera_lost('Synthetic disconnect')
        wait_for(lambda: not robot.snapshot()['enabled'])
        assert robot.snapshot()['direction'] == 'stop'
    print('PASS: capped two-turn motor budget, consistent search side, early reacquisition, fresh clear-path selection, sensor/Stop/timeout/camera guards')


if __name__ == '__main__':
    search_pause_checks()
    protocol_checks()
    main()
