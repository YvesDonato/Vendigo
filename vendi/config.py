"""Configuration has no import-time device access, API calls, or secrets."""

from dataclasses import dataclass, field
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_env():
    # Optional in offline mode. Existing environment takes precedence, then .env.local.
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env.local", override=False)
    load_dotenv(ROOT / ".env", override=False)


@dataclass(frozen=True)
class VoiceConfig:
    elevenlabs_api_key: str = field(default="", repr=False)
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    openai_api_key: str = field(default="", repr=False)
    openai_model: str = "gpt-5.6-luna"
    app_url: str = "http://127.0.0.1:3000"
    audio_input: str = ""
    audio_output: str = ""
    vosk_model_path: str = ""
    stt_provider: str = "elevenlabs"
    stt_model: str = "scribe_v2_realtime"
    end_silence: float = 1.2
    max_utterance: float = 45
    speech_rms_threshold: float = 250
    clips_dir: Path = ROOT / "vendi/audio/clips"
    cache_dir: Path = ROOT / ".vendi-cache"
    jingle_path: Path = ROOT / "food_robot/audio/jingle.wav"
    conversation_timeout: float = 30
    listen_timeout: float = 8
    request_timeout: float = 15
    echo_guard: float = 0.2
    funny_probability: float = 0.12
    phrase_probability: float = 0.65
    wake_cooldown: float = 5
    max_cached_clips: int = 128

    def __post_init__(self):
        for name in ("conversation_timeout", "listen_timeout", "request_timeout", "wake_cooldown", "max_utterance", "speech_rms_threshold"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.stt_provider not in ("elevenlabs", "vosk"):
            raise ValueError("VENDI_STT_PROVIDER must be elevenlabs or vosk")
        if not 0.3 <= self.end_silence <= 3:
            raise ValueError("VENDI_END_SILENCE must be between 0.3 and 3 seconds")
        if self.max_utterance <= self.end_silence:
            raise ValueError("VENDI_MAX_UTTERANCE must exceed VENDI_END_SILENCE")
        if not math.isfinite(self.echo_guard) or self.echo_guard < 0:
            raise ValueError("echo_guard must be finite and nonnegative")
        for name in ("funny_probability", "phrase_probability"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if self.max_cached_clips < 1:
            raise ValueError("max_cached_clips must be positive")

    @classmethod
    def from_env(cls):
        load_env()
        strings = {
            "elevenlabs_api_key": "ELEVENLABS_API_KEY", "elevenlabs_voice_id": "ELEVENLABS_VOICE_ID",
            "elevenlabs_model": "ELEVENLABS_MODEL", "openai_api_key": "OPENAI_API_KEY",
            "openai_model": "OPENAI_MODEL", "audio_input": "VENDI_AUDIO_INPUT",
            "app_url": "VENDIGO_APP_URL",
            "audio_output": "VENDI_AUDIO_OUTPUT", "vosk_model_path": "VENDI_VOSK_MODEL_PATH",
            "stt_provider": "VENDI_STT_PROVIDER", "stt_model": "VENDI_STT_MODEL",
        }
        numbers = {
            "conversation_timeout": "CONVERSATION_TIMEOUT", "listen_timeout": "VENDI_LISTEN_TIMEOUT",
            "request_timeout": "VENDI_REQUEST_TIMEOUT", "echo_guard": "VENDI_ECHO_GUARD",
            "funny_probability": "VENDI_FUNNY_PROBABILITY", "phrase_probability": "VENDI_PHRASE_PROBABILITY",
            "end_silence": "VENDI_END_SILENCE", "max_utterance": "VENDI_MAX_UTTERANCE",
            "speech_rms_threshold": "VENDI_SPEECH_RMS_THRESHOLD",
        }
        paths = {"clips_dir": "VENDI_CLIPS_DIR", "cache_dir": "VENDI_CACHE_DIR", "jingle_path": "VENDI_JINGLE_PATH"}
        values = {key: os.environ[env] for key, env in strings.items() if os.getenv(env)}
        values.update({key: float(os.environ[env]) for key, env in numbers.items() if os.getenv(env)})
        values.update({key: Path(os.environ[env]).expanduser() for key, env in paths.items() if os.getenv(env)})
        return cls(**values)
