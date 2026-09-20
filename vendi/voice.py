"""Public async API for the application's voice layer. No hardware commands live here."""

import asyncio
import logging
import random
import time
import uuid

from vendi.audio.audio_manager import AudioManager, Priority
from vendi.audio.backend import SoundDeviceBackend
from vendi.audio.jingle import ensure_jingle
from vendi.audio.phrase_manager import PhraseManager
from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent
from vendi.conversation.intents import Intent
from vendi.errors import AudioInterrupted, VoiceFailure
from vendi.events import EventType, VoiceEvent
from vendi.speech.stt import VoskSTT
from vendi.speech.scribe import ScribeSTT
from vendi.speech.turn import is_hesitation
from vendi.speech.tts import ElevenLabsTTS
from vendi.speech.wake_word import TranscriptWakeWord
from vendi.speech.yes_no import YesNo, classify_yes_no
from vendi.voice_state import StateMachine, VoiceState as S


class VendiVoice:
    def __init__(self, config=None, *, backend=None, tts=None, stt=None, agent=None,
                 context=None, wake_word=None, on_event=None, on_speech=None, rng=None):
        self.config = config or VoiceConfig.from_env()
        self.on_event = on_event or (lambda event: None)
        self.on_speech = on_speech or (lambda text: None)
        self.session_id = None
        self._session_kind = None
        self.machine = StateMachine(lambda state: self._emit(EventType.STATE_CHANGED, state=state.value))
        self.audio = AudioManager(backend or SoundDeviceBackend(self.config.audio_input, self.config.audio_output),
                                  self.machine.activity, self.config.echo_guard)
        self.tts = tts or ElevenLabsTTS(self.config)
        self.stt = stt or (ScribeSTT(self.config) if self.config.stt_provider == "elevenlabs" else
                          VoskSTT(self.config.vosk_model_path, self.config.end_silence,
                                  self.config.max_utterance, self.config.speech_rms_threshold))
        self.agent = agent or ConversationAgent(self.config, context)
        self.wake_word = wake_word or TranscriptWakeWord(self.config.wake_cooldown)
        self.rng = rng or random.Random()
        self.phrases = PhraseManager(self.rng, self.config.funny_probability)
        self._roaming_task = self._loop_task = self._timer_task = self._turn_task = self._purchase_task = None
        self._turn_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._last_activity = time.monotonic()
        self._closed = False
        self._stopping = False
        self._stops_in_progress = 0
        self._generation = 0
        self._ending_session = None

    @property
    def state(self):
        return self.machine.state

    @property
    def mode(self):
        return self.machine.mode

    def _emit(self, event_type, **data):
        try:
            self.on_event(VoiceEvent(event_type, self.session_id, data))
        except Exception:
            # A consumer callback must not kill audio cleanup or start recursive error events.
            logging.getLogger(__name__).error("Vendi event consumer failed for %s", event_type.value)

    def _error(self, error):
        self.machine.activity(S.ERROR)
        self._emit(EventType.VOICE_ERROR,
                   component=error.component if isinstance(error, VoiceFailure) else "voice",
                   message=str(error) if isinstance(error, VoiceFailure) else "Voice operation failed; retry the interaction.",
                   recoverable=True)
        self.machine.activity(None)

    async def _say(self, text, priority, phrase=None, fallback=True):
        try:
            self.on_speech(text)
            path = self.tts.phrase_path(phrase) if phrase else None
            await asyncio.wait_for(self.audio.play(lambda: self.tts.stream(text, path), priority), timeout=60)
            if self.mode == S.CONVERSATION and hasattr(self.agent, "record_spoken"):
                self.agent.record_spoken(text)
            return True
        except AudioInterrupted:
            return False
        except Exception as error:
            self._error(error)
            if fallback:
                await self._fallback(priority, failed_text=text)
            return False

    async def _fallback(self, priority=Priority.CONVERSATION, failed_text=None):
        if self._stopping or self._closed:
            return
        phrase = self.phrases.choose("errors")
        try:
            self.on_speech(phrase.text)
            # This path NEVER makes a second provider call when ElevenLabs is down.
            await self.audio.play(lambda: self.tts.stream(phrase.text, self.tts.phrase_path(phrase), cached_only=True), priority)
            if self.mode == S.CONVERSATION and hasattr(self.agent, "record_spoken"):
                last_reply = getattr(getattr(self.agent, "session_context", None), "last_assistant_response", None)
                self.agent.record_spoken(phrase.text, replace_last=failed_text is not None and failed_text == last_reply)
        except AudioInterrupted:
            pass
        except Exception as error:
            self._error(error)  # Missing offline clip or unavailable speaker; still return control.

    async def _phrase(self, category, priority):
        phrase = self.phrases.choose(category)
        return await self._say(phrase.text, priority, phrase)

    async def speak(self, text, priority=Priority.CONVERSATION):
        """Trusted application speech. Dynamic TTS is cached and centrally scheduled."""
        if self._closed or self._stopping:
            return False
        return await self._say(text, priority)

    async def play_sales_line(self):
        if self.mode not in (S.IDLE, S.ROAMING_AUDIO) or self._closed or self._stopping:
            return False
        phrase = self.phrases.sales_line()
        return await self._say(phrase.text, Priority.ROAMING, phrase)

    async def personalized_callout(self, text):
        """Application supplies the wording; this layer does no person detection."""
        if self.mode not in (S.IDLE, S.ROAMING_AUDIO):
            return False
        return await self.speak(text, Priority.CALLOUT)

    async def start_roaming(self, wake_listening=False):
        if self._closed or self._stopping or self.mode not in (S.IDLE, S.ROAMING_AUDIO):
            return False
        if self._roaming_task and not self._roaming_task.done():
            return True
        self.machine.transition(S.ROAMING_AUDIO)
        self._roaming_task = asyncio.create_task(self._roam(wake_listening))
        return True

    async def _roam(self, wake_listening):
        try:
            jingle = ensure_jingle(self.config)
            first = True
            while self.mode == S.ROAMING_AUDIO:
                duration = self.rng.uniform(5, 8) if first else self.rng.uniform(8, 15)
                first = False
                started = time.monotonic()
                try:
                    await self.audio.play_jingle(jingle, duration)
                    # The offline backend has no real playback clock.
                    if not getattr(self.audio.backend, "realtime", True):
                        await asyncio.sleep(max(0, duration - (time.monotonic() - started)))
                except AudioInterrupted:
                    continue
                if wake_listening:
                    heard = await self._listen(2.5, Priority.ROAMING)
                    if heard and self.wake_word.detect(heard):
                        self._emit(EventType.WAKE_WORD_DETECTED)
                        # Hand off after relinquishing roaming; no self-cancel or self-await.
                        self._roaming_task = None
                        self.machine.transition(S.IDLE)
                        await self.enter_conversation(listen=True)
                        return
                    if heard is None:
                        return
                if self.rng.random() < self.config.phrase_probability:
                    await self.play_sales_line()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._error(error)
        finally:
            if self.mode == S.ROAMING_AUDIO:
                self.machine.transition(S.IDLE)

    async def stop_roaming(self):
        task, self._roaming_task = self._roaming_task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.mode == S.ROAMING_AUDIO:
            self.machine.transition(S.IDLE)

    async def _listen(self, timeout, priority=Priority.CONVERSATION):
        try:
            def activity():
                self._last_activity = time.monotonic()
            text = await self.audio.listen(self.stt, timeout, priority, on_activity=activity,
                on_ready=lambda: self._emit(EventType.LISTENING_READY))
            if text:
                self._emit(EventType.TRANSCRIPT_RECEIVED, text=text)
            return text
        except AudioInterrupted:
            return None
        except Exception as error:
            self._error(error)
            await self._fallback(priority)
            return None

    async def test_microphone(self):
        """A bounded dev capture through the same half-duplex audio owner."""
        await self.stop_roaming()
        return await self._listen(self.config.listen_timeout)

    async def say_customer_greeting(self):
        async with self._start_lock:
            if self._closed or self._stopping or self._purchase_task:
                return False
            generation = await self.stop_all_audio()
            if generation != self._generation or self._closed or self._stopping:
                return False
            self.session_id = uuid.uuid4().hex
            self._session_kind = "purchase"
            self.machine.transition(S.CUSTOMER_GREETING)
            self._purchase_task = asyncio.current_task()
        try:
            return await self._phrase("greeting", Priority.TRANSACTION)
        finally:
            self._purchase_task = None

    async def ask_purchase_question(self, transcripts=None):
        """Ask, listen, retry UNKNOWN once, and emit consent without invoking GPT.

        transcripts is an optional iterable for typed demos/application-provided STT.
        Omitting it opens a fresh microphone stream after each spoken question.
        """
        async with self._start_lock:
            if self._closed or self._stopping or self._purchase_task:
                return YesNo.UNKNOWN
            if self.mode != S.CUSTOMER_GREETING:
                generation = await self.stop_all_audio()
                if generation != self._generation or self._closed or self._stopping:
                    return YesNo.UNKNOWN
                self.session_id = uuid.uuid4().hex
                self._session_kind = "purchase"
            self._purchase_task = asyncio.current_task()
            self.machine.transition(S.WAITING_FOR_YES_NO)
        supplied = iter(transcripts) if transcripts is not None else None
        answer = YesNo.UNKNOWN
        reason = "unrecognized"
        try:
            if not await self._phrase("question", Priority.TRANSACTION):
                reason = "speech_failed"
                return answer
            for attempt in range(2):
                text = next(supplied, "") if supplied is not None else await self._listen(self.config.listen_timeout, Priority.TRANSACTION)
                if text is None:
                    reason = "input_failed"
                    return answer
                answer = classify_yes_no(text)
                if answer != YesNo.UNKNOWN:
                    event = EventType.PURCHASE_ACCEPTED if answer == YesNo.YES else EventType.PURCHASE_DECLINED
                    self._emit(event)
                    await self._phrase("yes" if answer == YesNo.YES else "no", Priority.TRANSACTION)
                    reason = answer.value.lower()
                    return answer
                if attempt == 0:
                    if not await self._phrase("repeat", Priority.TRANSACTION):
                        reason = "speech_failed"
                        return answer
            await self._phrase("goodbye", Priority.TRANSACTION)
            return answer
        except asyncio.CancelledError:
            reason = "interrupted"
            raise
        finally:
            self._purchase_task = None
            self._return_control(reason)

    async def feed_wake_transcript(self, transcript, listen=False):
        if self._closed or self._stopping or self.mode not in (S.IDLE, S.ROAMING_AUDIO):
            return False
        if not self.wake_word.detect(transcript):
            return False
        self._emit(EventType.WAKE_WORD_DETECTED)
        return await self.enter_conversation(listen=listen)

    async def listen_for_wake_word(self, listen=False):
        """Temporary wake capture in a silent window; never transcribes playing jingles."""
        if self.mode not in (S.IDLE, S.ROAMING_AUDIO):
            return False
        roaming = self.mode == S.ROAMING_AUDIO
        await self.stop_roaming()
        text = await self._listen(self.config.listen_timeout, Priority.CALLOUT)
        detected = await self.feed_wake_transcript(text or "", listen=listen)
        if not detected and roaming:
            await self.start_roaming()
        return detected

    async def enter_conversation(self, listen=False):
        async with self._start_lock:
            if self._closed or self._stopping or self.mode not in (S.IDLE, S.ROAMING_AUDIO):
                return False
            generation = self._generation
            await self.stop_roaming()
            if generation != self._generation or self._closed or self._stopping:
                return False
            self.session_id = uuid.uuid4().hex
            self._session_kind = "conversation"
            self.agent.reset()
            self.machine.transition(S.CONVERSATION)
            self._emit(EventType.PAUSE_MOVEMENT_REQUESTED, reason="customer_conversation")
            self._emit(EventType.CONVERSATION_STARTED)
            self._turn_task = asyncio.current_task()
        try:
            if not await self._phrase("wake", Priority.CONVERSATION):
                self._return_control("speech_failed")
                return False
        finally:
            self._turn_task = None
        self._last_activity = time.monotonic()
        self._timer_task = asyncio.create_task(self._watch_inactivity())
        if listen:
            self._loop_task = asyncio.create_task(self._conversation_loop())
        return True

    async def _conversation_loop(self):
        failures = 0
        while self.mode == S.CONVERSATION:
            remaining = self.config.conversation_timeout - (time.monotonic() - self._last_activity)
            if remaining <= 0:
                return
            # Keep one capture open through idle conversation time; reopening every
            # eight seconds creates gaps where the start of a sentence can disappear.
            text = await self._listen(remaining)
            if text is None:
                failures += 1
                if failures < 2 and self.mode == S.CONVERSATION:
                    self._last_activity = time.monotonic()
                    continue  # One fresh connection after the prerecorded fallback.
                await self.end_conversation("input_failed")
                return
            failures = 0
            if text:
                await self.handle_transcript(text)
            else:
                # Silence is not a turn, an error, or a reason for an LLM call.
                await asyncio.sleep(0.05)

    async def handle_transcript(self, transcript):
        async with self._turn_lock:
            if self.mode != S.CONVERSATION or not transcript.strip():
                return None
            if is_hesitation(transcript):
                self._last_activity = time.monotonic()
                return None
            session = self.session_id
            self._turn_task = asyncio.current_task()
            self._last_activity = time.monotonic()
            try:
                reply = await self.agent.respond(transcript)
                if self.session_id != session or self.mode != S.CONVERSATION:
                    return None
                if reply.intent == Intent.END_CONVERSATION:
                    await self._phrase("goodbye", Priority.CONVERSATION)
                    self._return_control("customer_finished")
                else:
                    if reply.intent:
                        self._emit(EventType.INTENT_REQUESTED, intent=reply.intent.value, product_id=reply.product_id)
                    await self.speak(reply.text)
                return reply
            except Exception as error:
                self._error(error)
                await self._fallback()
                return None
            finally:
                self._last_activity = time.monotonic()
                self._turn_task = None

    async def _watch_inactivity(self):
        while self.mode == S.CONVERSATION:
            remaining = self.config.conversation_timeout - (time.monotonic() - self._last_activity)
            if remaining > 0:
                await asyncio.sleep(remaining)
            elif self._turn_task:
                await asyncio.sleep(0.1)  # A bounded provider/speaker turn is active, not inactivity.
            else:
                await self.end_conversation("timeout")
                return

    async def end_conversation(self, reason="application"):
        if self._session_kind != "conversation" or self._ending_session == self.session_id:
            return
        session = self._ending_session = self.session_id
        generation = self._generation
        try:
            await self._cancel_tasks(include_roaming=False)
            await self.audio.stop_all()
            if generation != self._generation or self.session_id != session or self._stopping:
                return
            await self._phrase("goodbye", Priority.CONVERSATION)
            if self.session_id == session:
                self._return_control(reason)
        finally:
            if self._ending_session == session:
                self._ending_session = None

    async def _cancel_tasks(self, include_roaming=True):
        names = ["_loop_task", "_timer_task", "_turn_task", "_purchase_task"]
        if include_roaming:
            names.append("_roaming_task")
        current = asyncio.current_task()
        tasks = {getattr(self, name) for name in names if getattr(self, name) not in (None, current)}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for name in names:
            if getattr(self, name) is not current:
                setattr(self, name, None)

    def _return_control(self, reason):
        kind = self._session_kind
        self._session_kind = None
        if self.mode != S.IDLE:
            if self.mode != S.RETURNING:
                self.machine.transition(S.RETURNING)
            self.machine.transition(S.IDLE)
        if kind == "conversation":
            self._emit(EventType.CONVERSATION_ENDED, reason=reason)
            self.agent.reset()
        if kind:
            self._emit(EventType.INTERACTION_COMPLETE, reason=reason)
        self.session_id = None
        for task in (self._timer_task, self._loop_task):
            if task and task is not asyncio.current_task():
                task.cancel()

    async def stop_all_audio(self):
        """Cancel producers AND audio, preventing delayed speech or jingle restarts."""
        self._stops_in_progress += 1
        self._generation += 1
        generation = self._generation
        self._stopping = True
        try:
            await self._cancel_tasks()
            await self.audio.stop_all()
            self._return_control("stopped")
        finally:
            self._stops_in_progress -= 1
            self._stopping = self._stops_in_progress > 0
        return generation

    async def close(self):
        if self._closed:
            return
        self._closed = True
        await self.stop_all_audio()
        await self.audio.close()
        await self.tts.close()
        await self.agent.close()
        if hasattr(self.stt, "close"):
            await self.stt.close()
