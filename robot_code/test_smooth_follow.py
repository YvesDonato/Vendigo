"""Run with staged iPlanner on PYTHONPATH; synthetic camera/controller only."""

from contextlib import contextmanager
from copy import deepcopy
import threading
import time
from types import SimpleNamespace

import numpy as np

from camera_live import Relay
from person_follow import PersonFollower, front_approach_allowed, horizontal_direction
from rgb_obstacles import Calibration, Observation
from robot_steering import TURN_BURST_MS, TURN_SETTLE_SECONDS, RobotSteering, WaitingForRobot, front_approach, following_intent, motor_output_stopped
from test_robot_steering import wait_for


def policy_checks():
    follower = PersonFollower.__new__(PersonFollower)
    follower.reset_target()
    follower.gap, follower.search_direction = .25, 'left'
    def target(center, ident=8, kind='person'):
        p = dict(box=[center-.12,.1,center+.12,.9], score=.9, range_m=1.)
        p.update(kind='feet') if kind == 'feet' else p.update(track_id=ident)
        return p
    def step(people, now):
        selected = follower.select_target(dict(people=deepcopy(people), target=None), now)
        return selected, follower.choose_direction(selected, now)

    centers = [.339,.341,.339,.341,.37,.39,.65,.661,.659,.661,.63,.61]
    expected = ['left']*5 + ['straight']*2 + ['right']*4 + ['straight']
    actions = [step([target(x)], 10+i*.1)[1]['direction'] for i,x in enumerate(centers)]
    assert actions == expected, actions
    assert horizontal_direction(target(.67)['box'], 'left') == 'right'
    assert horizontal_direction(target(.40)['box'], 'left') == 'straight', 'Left correction did not release into the wider forward band'
    assert horizontal_direction(target(.60)['box'], 'right') == 'straight', 'Right correction did not release into the wider forward band'
    raw_changes = sum(horizontal_direction(target(a)['box']) != horizontal_direction(target(b)['box'])
                      for a,b in zip(centers,centers[1:]))
    new_changes = sum(a != b for a,b in zip(actions,actions[1:]))
    assert new_changes < raw_changes
    now = time.monotonic()
    tracking = dict(people=[target(.4)], target=0)
    clear = Observation(np.array([[2.,0.]]), now, Calibration())
    assert front_approach_allowed(tracking, clear, now)
    assert not front_approach_allowed(tracking, clear, now, 'left')
    sensor = dict(connected=True, enabled=True, stop_distance_cm=25, distance_cm=90.,
                  distance_age_ms=10, distance_blocked=False, follow_direction='left', follow_age_s=.1)
    assert front_approach(dict(direction='left', front_approach_clear=True),sensor)['direction']=='left'
    missing = dict(direction='stop',tracking=dict(people=[],target=None),clear_motion_options=['stop','left','straight','right'])
    assert following_intent(missing,sensor)['direction']=='stop', 'No configured scan must preserve the original search/wait'
    assert following_intent(missing,dict(sensor,follow_direction='straight'))['direction']=='straight'
    stopped=dict(direction='stop',speed=0,pwm1_duty=0,pwm2_duty=0,driver_enabled=False)
    assert motor_output_stopped(stopped)
    assert not motor_output_stopped(dict(stopped,pwm1_duty=False)), 'Boolean PWM accepted as confirmed zero output'

    follower.reset_target()
    body, feet, other = target(.5), target(.5,kind='feet'), target(.5,ident=7)
    step([body], 20.)
    step([feet], 20.1)
    assert follower.selected_body_id == 8 and follower.selected_body_seen_at == 20.
    assert step([other],20.2)[0]['target'] is None
    assert step([body],20.3)[0]['target'] == 0
    step([feet],20.4)
    step([feet],22.31)
    assert follower.selected_body_id is None, 'Feet kept an expired body ID alive'
    assert step([other],22.4)[0]['target'] == 0, 'Associated new ID permanently locked out'
    assert follower.selected_body_id == 7
    follower.reset_target()
    step([body],30.)
    step([feet],31.6)
    step([],31.7)
    assert step([other],32.1)[0]['target'] is None, 'Expired body ID bypassed full target-loss wait'
    assert step([other],33.71)[0]['target'] == 0
    step([body],29.)
    assert follower.selected_body_id == 8, 'Clock rollback did not reset target memory'
    print(f'PASS: jitter direction changes {raw_changes}->{new_changes}; bounded body/feet ID memory, shared centring, forward-only hold')


@contextmanager
def fake_robot(search_rotation_seconds=None):
    relay = Relay(SimpleNamespace(max_frame_age=.5, follow_person=True))
    robot = RobotSteering(relay,'http://127.0.0.1','a'*64,255,255,25,search_rotation_seconds)
    relay.steering = robot
    calls = []
    state = dict(actual='stop',expiry=0.,delay=0.,drive_error=False,stop_error=False,cancel_status=False,
                 distance_cm=80.,distance_age_ms=10,
                 late_status_frame_at=None)
    def publish(direction='left', received=None, target=True):
        with relay.condition:
            relay.sequence += 1
            f=SimpleNamespace(id=relay.sequence,generation=relay.generation,
                              received=time.monotonic() if received is None else received,jpeg=b'test')
            relay.latest=f
        relay.model_ready=True
        people=[dict(box=[.1,.1,.3,.9],score=.9,range_m=1.)] if target else []
        relay.publish_decision(f,dict(direction=direction,reason='Synthetic',source='vlm',latency_s=.05,
                                     tracking=dict(people=people,target=0 if target else None),
                                     clear_motion_options=['stop','straight','left','right'], clear_path_direction='straight'))
        return f
    def request(path,fields=None):
        calls.append((time.monotonic(),path,deepcopy(fields)))
        if path == '/stop':
            if state['stop_error']:
                raise WaitingForRobot('Synthetic lost stop acknowledgement')
            state['actual']='stop'
            return dict(ok=True)
        if path == '/arm':
            return dict(session=42)
        if path == '/drive':
            state['actual']=fields['direction']
            state['expiry']=time.monotonic()+fields['lease_ms']/1000
            time.sleep(state['delay'])
            if state['drive_error']:
                state['drive_error']=False
                raise WaitingForRobot('Synthetic timeout after accepted drive')
        if path == '/status' and state['cancel_status']:
            state['cancel_status']=False
            robot.action('stop')
        if path == '/status' and state['late_status_frame_at'] is not None and time.monotonic()>=state['late_status_frame_at']:
            state['late_status_frame_at']=None
            time.sleep(.3)
            publish('straight')
        if time.monotonic()>=state['expiry']:
            state['actual']='stop'
        blocked=state['distance_cm'] is None or state['distance_cm']<=25 or state['distance_age_ms']>200
        if state['actual']=='straight' and blocked:
            state['actual']='stop'
        speed=255 if state['actual']!='stop' else 0
        return dict(ok=True,firmware='lordbot-jev-2',max_speed=255,direction=state['actual'],speed=speed,
                    pwm1_duty=speed,pwm2_duty=speed,driver_enabled=bool(speed),distance_guard=True,
                    distance_cm=state['distance_cm'],distance_age_ms=state['distance_age_ms'],distance_blocked=blocked,stop_distance_cm=25)
    robot.request=request
    worker=threading.Thread(target=robot.run,daemon=True)
    publish();worker.start()
    try:
        wait_for(lambda:robot.snapshot()['connected'])
        yield relay,robot,state,calls,publish
    finally:
        relay.close();worker.join(timeout=3)
        assert not worker.is_alive()


def movement(calls):
    return [c for c in calls if c[1]=='/drive' and c[2]['speed']>0]


def burst_checks():
    with fake_robot() as (relay,robot,state,calls,publish):
        assert not movement(calls)
        old=publish();robot.action('arm')
        wait_for(lambda:bool(movement(calls)))
        first=movement(calls)[0]
        assert first[2]['speed']==255 and 80<=first[2]['lease_ms']<=TURN_BURST_MS
        wait_for(lambda:robot.snapshot()['turn_phase']=='observing')
        marker=len(calls)
        for _ in range(30):
            # New live images cannot substitute for a newly analyzed image.
            with relay.condition:
                relay.latest=SimpleNamespace(id=999,generation=relay.generation,received=time.monotonic(),jpeg=b'test')
            relay.snapshot()  # UI polling must not advance the turn phase.
            time.sleep(.01)
        assert len(movement(calls))==1
        assert not any(p in ('/arm','/drive') for _,p,_ in calls[marker:])
        assert any(p=='/status' for _,p,_ in calls[marker:]), 'Sonar starved while disarmed'
        relay.publish_decision(old,dict(direction='straight',reason='Late old inference',source='vlm',latency_s=.1))
        time.sleep(.04)
        assert len(movement(calls))==1, 'Old analyzed frame passed the post-turn barrier'
        publish('straight')
        wait_for(lambda:robot.snapshot()['direction']=='straight')
        marker=len(calls)
        for _ in range(15):
            publish('straight');time.sleep(.02)
        assert len(movement(calls[marker:]))>=3, 'Straight drive was unnecessarily pulsed'
        assert not any(p=='/stop' for _,p,_ in calls[marker:])
        robot.action('stop');time.sleep(.08)
        marker=len(calls);publish();time.sleep(.1)
        assert not movement(calls[marker:]) and not robot.snapshot()['enabled']

    # Early cancellation must still require a post-stop image, including an opposite turn.
    for desired,target in [('straight',True),('right',True),('stop',False)]:
        with fake_robot() as (relay,robot,state,calls,publish):
            publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
            first=movement(calls)[0][0]
            publish(desired,target=target)
            wait_for(lambda:robot.snapshot()['turn_phase']=='observing')
            stopped=next(t for t,p,_ in calls if p=='/stop' and t>first)
            assert stopped-first<.12, 'Fresh cancellation waited for the full burst'
            time.sleep(.15)
            assert len(movement(calls))==1, 'Pre-stop cancellation result immediately drove again'

    # Repeated corrections each need their own stop, settling interval and fresh inference.
    with fake_robot() as (relay,robot,state,calls,publish):
        publish();robot.action('arm')
        until=time.monotonic()+1.
        while time.monotonic()<until:
            publish();time.sleep(.02)
        turns=movement(calls)
        assert len(turns)>=3
        for first,second in zip(turns,turns[1:]):
            assert first[2]['lease_ms']<=TURN_BURST_MS
            stopped=next(t for t,p,_ in calls if p=='/stop' and first[0]<t<second[0])
            confirmed=next(t for t,p,_ in calls if p=='/status' and stopped<t<second[0])
            assert second[0]-confirmed>=TURN_SETTLE_SECONDS
        robot.action('stop')

    with fake_robot() as (relay,robot,state,calls,publish):
        publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
        wait_for(lambda:robot.snapshot()['turn_phase']=='observing')
        # This frame is newer than the Stop but inside the settling interval.
        stopped=next(t for t,p,_ in calls if p=='/status' and t>movement(calls)[0][0])
        publish('right',received=stopped+TURN_SETTLE_SECONDS/2)
        time.sleep(.15)
        assert len(movement(calls))==1, 'Frame from within the settling interval authorized movement'
        publish('right')
        wait_for(lambda:len(movement(calls))==2)
        assert movement(calls)[1][2]['direction']=='right'

    # Late successful replies and timeout-after-execution cannot extend or repeat a pulse.
    for timeout in (False,True):
        with fake_robot() as (relay,robot,state,calls,publish):
            state.update(delay=.18,drive_error=timeout)
            publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
            first=movement(calls)[0][0]
            wait_for(lambda:robot.snapshot()['turn_phase']=='observing')
            stopped=next(t for t,p,_ in calls if p=='/stop' and t>first)
            assert stopped-first<.25, 'Late reply restarted the burst timer'
            time.sleep(.12)
            assert len(movement(calls))==1

    with fake_robot() as (relay,robot,state,calls,publish):
        publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
        state['stop_error']=True
        wait_for(lambda:not robot.snapshot()['enabled'])
        assert len(movement(calls))==1, 'Failed Stop permitted another pulse'

    with fake_robot() as (relay,robot,state,calls,publish):
        publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
        wait_for(lambda:robot.snapshot()['turn_phase']=='observing')
        start=time.monotonic()
        state['late_status_frame_at']=start+1.8
        wait_for(lambda:not robot.snapshot()['enabled'])
        assert time.monotonic()-start<2.5 and len(movement(calls))==1, 'Late status/fresh frame extended recovery beyond its deadline'

    with fake_robot() as (relay,robot,state,calls,publish):
        publish();robot.action('arm');wait_for(lambda:bool(movement(calls)))
        state['cancel_status']=True
        wait_for(lambda:not robot.snapshot()['enabled'])
        time.sleep(.1)
        assert len(movement(calls))==1, 'Stop during status check was ignored'

    with fake_robot() as (relay,robot,state,calls,publish):
        publish(received=time.monotonic()-.29);robot.action('arm');time.sleep(.06)
        assert not movement(calls), 'Insufficient camera budget sent a tiny turn'
        publish();wait_for(lambda:bool(movement(calls)))
        relay.camera_lost('Synthetic camera loss')
        wait_for(lambda:not robot.snapshot()['enabled'])
        assert len(movement(calls))==1
    print('PASS: bounded single-command turns, post-stop analyzed-frame barrier, continuous forward, Stop/camera/timeout/recovery guards')


if __name__=='__main__':
    policy_checks()
    burst_checks()
