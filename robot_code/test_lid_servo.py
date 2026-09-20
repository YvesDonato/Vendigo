"""Check the physical lid API; explicitly commands 180 degrees with wheels stopped."""

import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-url', default='http://192.168.8.100')
    args = parser.parse_args()
    token = Path(__file__).with_name('control.token').read_text().strip()
    opener = build_opener(ProxyHandler({}))

    def request(path, fields=None, authenticated=True):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + token
        body = None if fields is None else urlencode(fields).encode('ascii')
        with opener.open(Request(args.robot_url + path, data=body, headers=headers), timeout=3) as response:
            return json.load(response)

    before = request('/status')
    assert before['armed'] is False and before['speed'] == 0 and before['driver_enabled'] is False, 'Stop steering first'
    assert before['servo_pin'] == 25
    for angle, authenticated, expected in ((180, False, 401), (181, True, 400), (-1, True, 400)):
        try:
            request('/servo', {'angle': angle}, authenticated)
        except HTTPError as error:
            assert error.code == expected
        else:
            raise AssertionError('Invalid/unauthenticated servo request accepted')
    assert request('/status')['servo_angle'] == before['servo_angle'], 'Rejected request moved servo'
    command = request('/servo', {'angle': 180})
    assert command['ok'] is True
    time.sleep(1)
    after = request('/status')
    assert after['servo_enabled'] and after['servo_angle'] == 180 and after['servo_pulse_us'] == 2400
    assert after['servo_frequency_hz'] == 50 and after['servo_pwm_duty'] == 7864
    assert after['armed'] is False and after['driver_enabled'] is False
    for key in ('speed', 'pwm1_duty', 'pwm2_duty'):
        assert after[key] == 0, 'Lid command changed motor output'
    for key in ('pwm1_frequency_hz', 'pwm2_frequency_hz'):
        assert after[key] == before[key] and after[key] != 50, 'Servo reconfigured motor PWM'
    report = dict(angle_commanded=180, pulse_us=2400, servo_hz=50,
                  motor_pwm_hz=[after['pwm1_frequency_hz'], after['pwm2_frequency_hz']],
                  motors_stopped=True, invalid_requests_rejected=True, physical_angle_measured=False)
    Path(__file__).with_name('lid-servo-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('PASS: 180-degree servo output verified; wheels remain stopped. No position feedback is available.')


if __name__ == '__main__':
    main()
