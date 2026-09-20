"""Run the real host loop against a fake controller; no robot or GPU."""

from io import BytesIO
import threading
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image

from camera_live import Relay
from robot_steering import RobotSteering
from test_robot_steering import wait_for


def main():
    relay = Relay(SimpleNamespace(max_frame_age=.5, openjev_turns_only=True))
    robot = RobotSteering(relay, 'http://127.0.0.1', 'a' * 64, 255, 255, 50)
    relay.steering = robot
    image = BytesIO()
    Image.fromarray(np.zeros((24, 32, 3), dtype=np.uint8)).save(image, format='JPEG')
    tracking = dict(people=[dict(box=[.1, .1, .3, .9], score=.9, range_m=1.)], target=0)
    state = dict(desired='straight', actual='stop', stuck=False, cancel=False)
    calls = []

    def publish():
        while not relay.stopping.is_set():
            frame = relay.record_frame(image.getvalue())
            relay.model_ready = True
            relay.publish_decision(frame, dict(direction=state['desired'], reason='Test', source='vlm',
                                               latency_s=.07, tracking=tracking, front_approach_clear=False))
            relay.stopping.wait(.01)

    def request(path, fields=None):
        calls.append((path, None if fields is None else dict(fields)))
        if path == '/stop':
            state['actual'] = 'stop'
        elif path == '/arm':
            return dict(session=42)
        elif path == '/drive':
            state['actual'] = fields['direction']
        elif path == '/status' and state['cancel']:
            state['cancel'] = False
            robot.action('stop')
        actual = 'straight' if state['stuck'] else state['actual']
        pwm = 0 if actual == 'stop' else 255
        return dict(ok=True, firmware='lordbot-jev-2', max_speed=255, direction=actual, speed=pwm,
                    pwm1_duty=pwm, pwm2_duty=pwm, driver_enabled=pwm > 0,
                    distance_guard=True, distance_cm=100., distance_age_ms=10,
                    distance_blocked=False, stop_distance_cm=50)

    robot.request = request
    camera = threading.Thread(target=publish, daemon=True)
    worker = threading.Thread(target=robot.run, daemon=True)
    camera.start(); worker.start()
    try:
        wait_for(lambda: robot.snapshot()['connected'] and relay.decision is not None)
        robot.action('arm')
        wait_for(lambda: robot.snapshot()['direction'] == 'straight')
        marker = len(calls)
        state['desired'] = 'left'
        wait_for(lambda: robot.snapshot()['direction'] == 'left')
        transition = calls[marker:]
        stop = next(i for i, (p, _) in enumerate(transition) if p == '/stop')
        status = next(i for i, (p, _) in enumerate(transition) if p == '/status')
        turn = next(i for i, (p, f) in enumerate(transition) if p == '/drive' and f['direction'] == 'left')
        assert stop < status < turn, 'Turn began without confirming stopped output'
        marker = len(calls)
        time.sleep(.16)
        assert not any(p == '/stop' for p, _ in calls[marker:]), 'Same-direction renewals repeatedly stopped the turn'
        marker = len(calls)
        state['desired'] = 'straight'
        wait_for(lambda: robot.snapshot()['direction'] == 'straight')
        assert not any(p == '/stop' for p, _ in calls[marker:]), 'Rule forward has an unnecessary extra stop'

        state['stuck'] = True
        marker = len(calls)
        state['desired'] = 'right'
        wait_for(lambda: robot.snapshot()['message'].startswith('Paused:'))
        assert not any(p == '/drive' and f['direction'] == 'right' for p, f in calls[marker:])
        state['stuck'] = False
        wait_for(lambda: robot.snapshot()['direction'] == 'right')

        state['desired'] = 'straight'
        wait_for(lambda: robot.snapshot()['direction'] == 'straight')
        state['cancel'] = True
        marker = len(calls)
        state['desired'] = 'left'
        wait_for(lambda: not robot.snapshot()['enabled'])
        time.sleep(.2)
        assert not any(p == '/drive' and f['direction'] == 'left' for p, f in calls[marker:]), 'Stop during handoff allowed a turn'
    finally:
        relay.close(); camera.join(timeout=2); worker.join(timeout=2)
    assert not worker.is_alive()
    print('PASS: confirmed zero motor output before turns, continuous renewal, direct return to rule forward, failed stop blocks turn, explicit Stop wins during handoff')


if __name__ == '__main__':
    main()
