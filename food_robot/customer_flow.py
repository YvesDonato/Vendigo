"""Hardware-independent customer interaction flow; see CUSTOMER_FLOW.md."""

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Protocol
import uuid


class State(str, Enum):
    ROAMING = "roaming"
    APPROACH = "waiting_for_customer"
    ANSWER = "waiting_for_answer"
    ORDER = "waiting_for_order"
    LEAVING = "leaving"


class Ports(Protocol):
    """Commands must succeed or raise; speech completes before returning."""

    def stop_jingle(self): ...
    def start_jingle(self): ...
    def stop_motion(self): ...
    def speak(self, text: str): ...
    def listen(self, session_id: str): ...
    def stop_listening(self): ...
    def show_order_qr(self, session_id: str): ...
    def hide_order_qr(self): ...
    def leave(self, session_id: str): ...


@dataclass(frozen=True)
class Config:
    close_distance_m: float = 1.5
    approach_timeout_s: float = 20
    answer_timeout_s: float = 12
    order_timeout_s: float = 180
    cooldown_s: float = 120
    observation_max_age_s: float = 2

    def __post_init__(self):
        for value in vars(self).values():
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Configuration values must be finite and positive")


class CustomerFlow:
    def __init__(self, ports: Ports, config=None, clock=time.monotonic):
        self.ports = ports
        self.config = config or Config()
        self.clock = clock
        self.state = State.ROAMING
        self.session_id = None
        self.customer_id = None
        self.deadline = None
        self.cooldowns = {}

    def customer_seen(self, customer_id, shirt_color=None):
        """Use a stable tracker ID, not face recognition or a person's name."""
        now = self.clock()
        self.cooldowns = {key: end for key, end in self.cooldowns.items() if end > now}
        if self.state != State.ROAMING or not customer_id or customer_id in self.cooldowns:
            return False
        self.customer_id = customer_id
        self.session_id = uuid.uuid4().hex
        self.state = State.APPROACH
        self.ports.stop_jingle()
        self.ports.stop_motion()
        # Only describe visible clothing; uncertain classifications use a generic greeting.
        colors = {"white", "black", "red", "blue", "green", "yellow", "orange",
                  "purple", "pink", "brown", "gray", "grey"}
        greeting = f"Hello, person in the {shirt_color} shirt!" if shirt_color in colors else "Hello there!"
        self.ports.speak(f"{greeting} Would you like to come over and see the food menu?")
        self.deadline = self.clock() + self.config.approach_timeout_s
        return True

    def distance(self, customer_id, meters, observed_at):
        """Distance must belong to the selected customer and use this clock's timebase."""
        self.tick()
        if self.state != State.APPROACH or customer_id != self.customer_id:
            return False
        age = self.clock() - observed_at
        if not all(math.isfinite(v) for v in (meters, age)):
            return False
        if not (0 <= age <= self.config.observation_max_age_s and 0 < meters <= self.config.close_distance_m):
            return False
        self.state = State.ANSWER
        self.ports.speak("Hi! Would you like to buy some food?")
        self.ports.listen(self.session_id)
        self.deadline = self.clock() + self.config.answer_timeout_s
        return True

    def answer(self, session_id, answer):
        self.tick()
        if self.state != State.ANSWER or session_id != self.session_id:
            return False
        if answer not in ("yes", "no"):
            return False
        self.ports.stop_listening()
        if answer == "no":
            self._finish("No problem! Have a nice day.")
        else:
            self.state = State.ORDER
            self.ports.show_order_qr(self.session_id)
            self.ports.speak("Great! Kindly scan the QR code to place your order.")
            self.deadline = self.clock() + self.config.order_timeout_s
        return True

    def order_completed(self, session_id):
        """Call only from the ordering backend after this session's order is confirmed."""
        self.tick()
        if self.state != State.ORDER or session_id != self.session_id:
            return False
        self._finish("Thank you for your order! Have a lovely day.")
        return True

    def tick(self):
        """Call regularly, including when sensors and speech produce no events."""
        if self.deadline is None or self.clock() < self.deadline:
            return
        if self.state == State.APPROACH:
            self._finish()
        elif self.state == State.ANSWER:
            self._finish("No worries! Have a nice day.")
        elif self.state == State.ORDER:
            self._finish("I'll let you take your time. Have a nice day.")

    def _finish(self, message=None):
        self.state = State.LEAVING
        self.deadline = None
        self.ports.stop_listening()
        self.ports.hide_order_qr()
        if message:
            self.ports.speak(message)
        self.cooldowns[self.customer_id] = self.clock() + self.config.cooldown_s
        self.ports.leave(self.session_id)
        self.ports.start_jingle()

    def departure_completed(self, session_id):
        """Navigation acknowledges departure before another customer can be selected."""
        if self.state != State.LEAVING or session_id != self.session_id:
            return False
        self.state = State.ROAMING
        self.session_id = self.customer_id = None
        return True

    def shutdown(self):
        # Attempt every cleanup even if one device fails.
        try:
            self.ports.stop_motion()
        finally:
            try:
                self.ports.stop_listening()
            finally:
                try:
                    self.ports.hide_order_qr()
                finally:
                    self.ports.stop_jingle()


class DemoPorts:
    """Print commands without activating audio, cameras, or motors."""

    def __getattr__(self, name):
        return lambda *args: print(f"{name}: {' '.join(map(str, args))}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simulate a customer conversation; no hardware used.")
    parser.add_argument("--answer", choices=("yes", "no"), default="yes")
    args = parser.parse_args()
    flow = CustomerFlow(DemoPorts())
    try:
        flow.customer_seen("demo-customer", "white")
        flow.distance("demo-customer", 1.2, flow.clock())
        flow.answer(flow.session_id, args.answer)
        if args.answer == "yes":
            flow.order_completed(flow.session_id)
        flow.departure_completed(flow.session_id)
        print(f"Final state: {flow.state.value}")
    finally:
        flow.shutdown()
