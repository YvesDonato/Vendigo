from enum import Enum


class VoiceState(str, Enum):
    IDLE = "IDLE"
    ROAMING_AUDIO = "ROAMING_AUDIO"
    CUSTOMER_GREETING = "CUSTOMER_GREETING"
    WAITING_FOR_YES_NO = "WAITING_FOR_YES_NO"
    CONVERSATION = "CONVERSATION"
    SPEAKING = "SPEAKING"
    LISTENING = "LISTENING"
    RETURNING = "RETURNING"
    ERROR = "ERROR"


S = VoiceState
TRANSITIONS = {
    S.IDLE: {S.ROAMING_AUDIO, S.CUSTOMER_GREETING, S.WAITING_FOR_YES_NO, S.CONVERSATION, S.RETURNING},
    S.ROAMING_AUDIO: {S.IDLE, S.CUSTOMER_GREETING, S.WAITING_FOR_YES_NO, S.CONVERSATION, S.RETURNING},
    S.CUSTOMER_GREETING: {S.WAITING_FOR_YES_NO, S.RETURNING, S.CONVERSATION},
    S.WAITING_FOR_YES_NO: {S.RETURNING},
    S.CONVERSATION: {S.RETURNING, S.WAITING_FOR_YES_NO, S.CUSTOMER_GREETING},
    S.RETURNING: {S.IDLE},
}


class StateMachine:
    """Stable mode plus a temporary audio activity; no stale restore after a mode change."""

    def __init__(self, on_change=lambda state: None):
        self.mode = S.IDLE
        self.state = S.IDLE
        self._activity = None
        self._on_change = on_change

    def transition(self, mode):
        if mode != self.mode and mode not in TRANSITIONS.get(self.mode, set()):
            raise ValueError(f"Invalid voice transition: {self.mode.value} -> {mode.value}")
        self.mode = mode
        self._publish()

    def activity(self, state):
        if state not in (None, S.SPEAKING, S.LISTENING, S.ERROR):
            raise ValueError("Invalid audio activity")
        self._activity = state
        self._publish()

    def _publish(self):
        state = self._activity or self.mode
        if self.state != state:
            self.state = state
            self._on_change(state)
