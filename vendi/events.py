from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class EventType(str, Enum):
    PURCHASE_ACCEPTED = "PURCHASE_ACCEPTED"
    PURCHASE_DECLINED = "PURCHASE_DECLINED"
    INTERACTION_COMPLETE = "INTERACTION_COMPLETE"
    CONVERSATION_STARTED = "CONVERSATION_STARTED"
    CONVERSATION_ENDED = "CONVERSATION_ENDED"
    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    PAUSE_MOVEMENT_REQUESTED = "PAUSE_MOVEMENT_REQUESTED"
    INTENT_REQUESTED = "INTENT_REQUESTED"
    VOICE_ERROR = "VOICE_ERROR"
    STATE_CHANGED = "STATE_CHANGED"
    LISTENING_READY = "LISTENING_READY"
    TRANSCRIPT_RECEIVED = "TRANSCRIPT_RECEIVED"


@dataclass(frozen=True)
class VoiceEvent:
    type: EventType
    session_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
