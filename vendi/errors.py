class VoiceFailure(RuntimeError):
    """Safe, actionable message; provider responses and credentials are never forwarded."""

    def __init__(self, component, message):
        super().__init__(message)
        self.component = component


class AudioInterrupted(RuntimeError):
    """An audio request was superseded or explicitly stopped; not a device failure."""
