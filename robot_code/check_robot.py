"""Check flashed LordBot firmware; --exercise additionally runs brief motor pulses."""

import argparse
import json
from pathlib import Path
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path, default=Path(__file__).with_name("control.token"))
    parser.add_argument("--exercise", action="store_true", help="Wheels must be lifted; briefly energizes the motors")
    parser.add_argument("--speed", type=int, default=160, help="Exercise PWM, 1-255")
    args = parser.parse_args()
    if not 1 <= args.speed <= 255:
        parser.error("--speed must be between 1 and 255")
    token = args.token_file.read_text().strip()
    opener = build_opener(ProxyHandler({}))

    def request(path, data=None, *, auth=True, expected=200, timeout=3):
        headers = {"Authorization": "Bearer " + token} if auth else {}
        body = None if data is None else urlencode(data).encode()
        try:
            with opener.open(Request(args.url.rstrip("/") + path, body, headers), timeout=timeout) as response:
                assert response.status == expected
                return json.load(response)
        except HTTPError as error:
            assert error.code == expected, (error.code, error.read())

    def drive(session, sequence, direction="stop", speed=0, lease=150, expected=200):
        return request("/drive", dict(session=session, sequence=sequence, direction=direction,
                                     speed=speed, lease_ms=lease), expected=expected)

    request("/stop", {})
    try:
        time.sleep(.03)
        status = request("/status")
        assert status["firmware"] in ("lordbot-jev-1", "lordbot-jev-2") and status["speed"] == 0 and not status["armed"]
        assert status.get("forward_bits") == 92, "Flash the corrected forward mapping before testing motion"
        if status["firmware"] == "lordbot-jev-2":
            cutoff = status["stop_distance_cm"]
            request("/stop-distance", {"cm": cutoff}, auth=False, expected=401)
            for invalid in (9, 101, "50.5"):
                request("/stop-distance", {"cm": invalid}, expected=400)
            reply = request("/stop-distance", {"cm": cutoff})
            assert reply["distance_guard"] and reply["stop_distance_cm"] == cutoff
            assert not request("/status")["armed"]
        request("/status", auth=False, expected=401)
        session = request("/arm", {})["session"]
        drive(session, 1)
        drive(session, 1, expected=409)
        time.sleep(.25)
        status = request("/status")
        assert not status["armed"] and status["speed"] == 0
        drive(session, 2, expected=409)
        session = request("/arm", {})["session"]
        drive(session, 1, speed=256, expected=400)
        assert not request("/status")["armed"]
        session = request("/arm", {})["session"]
        drive(session, 1, lease=201, expected=400)
        assert not request("/status")["armed"]
        print("PASS: authentication, startup/stop, command expiry, stale sequence/session, speed and lease bounds", flush=True)

        if args.exercise:
            for direction in ("straight", "left", "right"):
                print("Brief lifted-wheel test:", direction, "PWM", args.speed, flush=True)
                session = request("/arm", {})["session"]
                for sequence in range(1, 7):
                    drive(session, sequence, direction, args.speed)
                    time.sleep(.05)
                state = request("/status")
                assert state["direction"] == direction and state["speed"] == args.speed
                assert state["driver_enabled"], state
                expected_duty = 256 if args.speed == 255 else args.speed
                assert state["pwm1_duty"] == state["pwm2_duty"] == expected_duty, state
                print("Verified PWM hardware duty:", state["pwm1_duty"], state["pwm2_duty"], flush=True)
                request("/stop", {})
                time.sleep(.25)
                assert request("/status")["speed"] == 0

            # Hold HTTP parsing open while the independent task must disable PWM.
            session = request("/arm", {})["session"]
            reply = drive(session, 1, "straight", args.speed)
            target = urlsplit(args.url)
            with socket.create_connection((target.hostname, target.port or 80), timeout=2) as stalled:
                stalled.sendall(("POST /drive HTTP/1.1\r\nHost: " + target.netloc
                                 + "\r\nContent-Type: application/x-www-form-urlencoded\r\n"
                                 + "Content-Length: 1000\r\n\r\nx").encode())
                time.sleep(.45)
            # WebServer may finish its 5 s body-read timeout before answering.
            # The device timestamp below checks the motor stopped independently.
            state = request("/status", timeout=8)
            lateness = (state["last_stop_ms"] - reply["expires_ms"]) & 0xffffffff
            assert not state["armed"] and state["speed"] == 0 and lateness <= 50, state
            print("PASS: independent motor watchdog stopped PWM", lateness, "ms after expiry during a stalled HTTP request", flush=True)
    finally:
        request("/stop", {})


if __name__ == "__main__":
    main()
