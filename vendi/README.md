# Vendi voice

Vendi is a concise, confident street vendor: an adult American female voice with
warmth, energy, and a little cheek. The Python package follows the existing
`food_robot` / headless Python architecture and runs independently of the website.
It does not import the web agent's navigation tools or issue hardware commands.

**Start with the laptop demo.** From the repository root, Python 3.9+ is sufficient
for the offline demo and tests; no dependencies, credentials, or devices are needed:

```bash
python3 -m vendi.voice_demo
python3 -m vendi.voice_demo --smoke
python3 -m unittest discover -s tests -p 'test_vendi*.py' -v
```

Offline mode explicitly simulates audio, STT, GPT, and a small sample inventory.
The same scheduler, state machine, consent classifier, events, and timeout logic
run in both offline and live modes. Spoken text, recognized `You:` transcripts, and
`Listening…` cues print to the terminal. Add `--debug` for raw JSON events.

**Enable real speech and conversation.** Install into an isolated environment:

```bash
python3 -m venv .venv-vendi
source .venv-vendi/bin/activate
python -m pip install -r vendi/requirements.txt
```

Add the following names to your existing `.env.local` without replacing unrelated
settings. The process environment takes precedence over `.env.local`, then `.env`.
Never put credentials in a `NEXT_PUBLIC_` variable. `.env.local` is ignored by Git.

```dotenv
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL=eleven_flash_v2_5
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
VENDI_AUDIO_OUTPUT=
VENDI_AUDIO_INPUT=
VENDI_STT_PROVIDER=elevenlabs
VENDI_STT_MODEL=scribe_v2_realtime
VENDI_END_SILENCE=1.2
VENDI_MAX_UTTERANCE=45
CONVERSATION_TIMEOUT=30
```

The demo uses Matilda, an adult American female voice with an upbeat alto delivery.
The voice is selected centrally by `ELEVENLABS_VOICE_ID` in `.env.local` (see `.env.example`). Audition the greeting and sales lines to check
delivery. The same voice ID, model, and settings generate every spoken line.
`ELEVENLABS_SPEECH_ENGINE_ID` belongs to the preserved web/headless integration;
Vendi's independent pipeline does not require a hosted Speech Engine. A `seng_`
ID is not a TTS voice ID.

`VENDI_AUDIO_INPUT` / `VENDI_AUDIO_OUTPUT` accept a PortAudio device index or name;
blank selects the system default. They are not legacy `arecord -D plughw:...`
arguments. Inspect the actual device names on each laptop/Pi:

```bash
python -m vendi.voice_demo --list-devices
```

Live mode streams microphone audio to ElevenLabs Scribe v2 realtime using the
same `ELEVENLABS_API_KEY`; this consumes STT credits. No local model download is
required. Conversation capture stays open while waiting for a customer; active
speech has its own 45-second budget. A 1.2-second pause ends a turn. Increase
`VENDI_END_SILENCE` up to 3 seconds for a more patient demo; this also delays replies.
`CONVERSATION_TIMEOUT` controls inactivity, not sentence length.

For optional offline recognition, set `VENDI_STT_PROVIDER=vosk` and
`VENDI_VOSK_MODEL_PATH=.vendi-cache/vosk-model-small-en-us-0.15`.
Install an unpacked English Vosk model. The
[official small English model](https://alphacephei.com/vosk/models) supports desktop
and Raspberry Pi use. An existing robot Vosk model directory can be reused.

```bash
mkdir -p .vendi-cache
curl --fail --location --output .vendi-cache/vosk.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q .vendi-cache/vosk.zip -d .vendi-cache
```

Pre-generate the library before a demo. This uses ElevenLabs API credits; completed
clips are reused on subsequent runs. Error lines generate first so an offline
fallback is available even if later generation fails.

```bash
python -m vendi.voice_demo --generate-clips
python -m vendi.voice_demo --check-providers
python -m vendi.voice_demo --live
```

**Test each behavior directly.** With the environment activated:

```bash
# 1. Random jingle/announcement sequence; Ctrl+C always closes the audio devices
python -m vendi.voice_demo --live --command roam --duration 30
# 2. Random normal/rare sales line
python -m vendi.voice_demo --live --command sales
# 3–4. Simulated customer consent, real prerecorded response audio, no GPT
python -m vendi.voice_demo --live --command yes
python -m vendi.voice_demo --live --command no
# Retry UNKNOWN once, then accept
python -m vendi.voice_demo --live --command yes --text 'not sure' --text yes
# 5. Manual Hey Vendi trigger, then microphone conversation until bye/timeout
python -m vendi.voice_demo --live --command wake --mic
# Typed turns still exercise real GPT → ElevenLabs
python -m vendi.voice_demo --live --command wake --text 'Tell me a quick joke' --text 'okay thanks'
# 6. Dynamic ElevenLabs speech, cached for reuse
python -m vendi.voice_demo --live --command tts --text 'Your snack guide has arrived.'
# 7. Bounded microphone/STT capture
python -m vendi.voice_demo --live --command stt
# Full spoken purchase question → mic → deterministic YES/NO → response
python -m vendi.voice_demo --live --command purchase
# Real providers without opening devices
python -m vendi.voice_demo --live --no-audio --command wake --text 'Tell me a quick joke' --text bye
# Real STT against a recorded mono, 16-bit PCM WAV fixture
python -m vendi.voice_demo --transcribe-file /absolute/path/to/customer.wav
# Read current inventory/prices from the existing web application
python -m vendi.voice_demo --live --app-url http://localhost:3000 --command wake
# Longer live demo, with microphone conversation and five-minute inactivity timeout
CONVERSATION_TIMEOUT=300 python -m vendi.voice_demo --live --command wake --mic
```

The first seven menu choices match these demo paths. Choice 8 runs the full
spoken purchase. Omitting `--live` uses explicit stubs. `--no-audio` disables both
devices and is for cloud-pipeline checks, not microphone tests. `--check-providers`
makes one short request to each provider and exits without device access.

**Files and responsibilities.** All implementation files below are new:

```text
vendi/
  __init__.py                  Public VendiVoice export
  config.py                    Environment, validated timings, paths
  errors.py                    Safe provider/device errors and interruption type
  events.py                    Correlated application-level events
  voice.py                     Public API, interaction lifecycles, task cancellation
  voice_state.py               Explicit mode transitions and speaking/listening activity
  voice_demo.py                Menu, scripted commands, provider checks, clip generation
  requirements.txt            Live-mode dependencies only
  README.md                    Setup, testing, deployment, integration
  audio/
    __init__.py
    audio_manager.py           One priority worker for microphone, speech, and music
    backend.py                 PortAudio streaming and explicit silent demo backend
    speech_pcm.py              Trim quiet TTS padding while retaining internal pauses
    phrase_manager.py          34 categorized phrases, rare humor, no consecutive repeats
    jingle.py                  Original synthesized fallback tune
    clips/README.md            Library generation and deployment instructions
  speech/
    __init__.py
    tts.py                     ElevenLabs streamed PCM, reusable WAVs, bounded dynamic cache
    stt.py                     Local streaming Vosk and scripted demo input
    scribe.py                  ElevenLabs realtime STT, complete turns, cancellation
    turn.py                    Speech activity, hesitation filtering, separate deadlines
    yes_no.py                  YES / NO / UNKNOWN without GPT
    wake_word.py               Replaceable wake interface and temporary transcript detector
  conversation/
    __init__.py
    agent.py                   Persona, GPT Responses API, full session history, response repair
    session.py                 Topic/product references, purchase steps, duplicate detection
    knowledge.py               Authoritative paid lifecycle and LID_OPEN_SECONDS = 7
    purchase_guide.py          Contextual question hints and procedural speech validation
    guardrails.py              Scoped shop/status claims; allows numbers and general knowledge
    context.py                 Facts interface, unknown/static facts, read-only Vendigo adapter
    intents.py                 Allowed intents, deterministic factual speech, endings
tests/test_vendi_voice.py      Offline behavior, failure, concurrency, and provider-contract tests
tests/test_vendi_turns.py      Late speech, natural pauses, complete transcripts, audio padding
tests/test_vendi_conversation.py  General questions, routing collisions, factual guards, follow-ups
tests/test_vendi_purchase_guide.py  Session memory, contextual references, paid lifecycle, authorization
```

Existing tracked files modified: `.env.example`, `.gitignore`, and root `README.md`.
Local `.env.local`, `.venv-vendi/`, generated clips, and `.vendi-cache/` are ignored.
Existing camera, ESP32, motor, payment, servo, storefront, legacy voice files,
and `food_robot` state-machine code are preserved.

**Audio ownership and latency.** `AudioManager` queues equal-priority jobs in order
and cancels a lower-priority active job when a higher-priority request arrives:

```text
1 transaction / customer interaction
2 active Hey Vendi conversation
3 application-provided personalized callout
4 roaming announcement / optional wake capture
5 jingle
```

Speech and microphone jobs use the same worker. Playback drains the PortAudio
speaker buffer before returning; capture starts after a configurable 200 ms echo
guard. Every listening turn opens a fresh input stream, closes it on endpoint,
silence, timeout, failure, or cancellation, and discards its buffered audio. The
microphone is never active while Vendi is speaking or playing music. Stop cancels
producer tasks as well as active/queued audio, so a delayed model reply cannot
restart speech after shutdown.

Roaming begins with 5–8 seconds of jingle, then uses 8–15 second segments. Each gap
has a 65% chance of a sales phrase; 12% of sales phrases are funny. Music stops
before speech and restarts afterward from the beginning. The repo's existing
`food_robot/audio/jingle.wav` is used by default. If it is missing, Vendi generates
an original short synthesized tune locally. No new music download is required.

ElevenLabs uses the [streaming speech endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/stream)
with Flash v2.5 by default and 24 kHz, 16-bit mono PCM. Playback starts after a small
120 ms buffer to smooth incoming chunks. Quiet leading/trailing padding is trimmed
with 100 ms of boundary padding retained; pauses inside speech are preserved.
Common phrases live under `audio/clips/<voice fingerprint>/<category>/`;
text hashes prevent stale wording. Dynamic speech uses an independently bounded
128-clip cache. Files become visible atomically only after a successful complete
download. Interrupted/failed downloads are discarded. The same voice/settings
fingerprint covers cached and dynamic speech; legacy clips of another voice are
not mixed in. Stop playback immediately on preemption; jingle pause does not depend
on a fade finishing.

ElevenLabs Scribe receives 100 ms PCM chunks as the customer speaks. Partial
transcripts never reach GPT. Committed segments are joined while speech continues;
the recognizer waits for the configured silence interval before returning a turn.
Speech activity refreshes conversation inactivity, so a customer starting late
does not lose the sentence at an eight-second capture boundary. Standalone STT and
purchase prompts use `VENDI_LISTEN_TIMEOUT` only as their speech-start deadline.
The optional local Vosk path also waits through brief pauses. YES/NO, clear endings, greetings, simple
menu requests, inventory/price lookups, and order/payment checks are deterministic.
UNKNOWN consent gets exactly one repeat, then a goodbye and `INTERACTION_COMPLETE`;
silence/UNKNOWN never implies purchase acceptance or decline.

GPT-5.6 Luna handles conversational turns that benefit from reasoning through the
[Responses API with structured output](https://developers.openai.com/api/docs/guides/structured-outputs).
Model selection comes from `OPENAI_MODEL`, responses are short, requests have a
timeout, and provider transport retries are disabled. `conversation_history` retains
every accepted user/assistant exchange for the active session; every model request
receives that history, including replies rendered by deterministic application code.
`history` is an alias to the same list. There is no six-exchange truncation.
The model receives a fresh application snapshot each relevant turn. It has no
tools for navigation, lids, payment authorization, shell access, or HTTP actions.
Validated intents are requests emitted to the application, never executed here.

Inventory/price/order/payment replies are rendered by deterministic code from
application facts. Unknown inventory is distinct from a verified empty inventory;
missing prices remain unknown. The prompt and output checks also constrain
unsolicited claims in social prose; these checks are defense in depth, not a formal
proof of arbitrary model text. User statements cannot set verified payment status.
General questions use GPT's knowledge and do not trigger menu intents just because
they contain a year, number, or words like "free" and "order". Deterministic routes
match explicit shop requests; ambiguous wording goes to the conversational model.
All accepted conversational replies, including deterministic ones, enter session
history so follow-ups retain their context. Vendi has no live news/search tool;
general knowledge is not guaranteed to reflect recent changes.
`VendigoContext` reads only `GET /api/state`, scopes inventory to one robot, and
requires an explicit `order_id` before exposing an order's status. The existing
demo storefront supplies no payment verification, so that adapter always
sets `payment_verified=False`.

**Conversation memory and purchase explanations.** `ConversationContext` in
`conversation/session.py` tracks `topic`, `last_intent`, `referenced_product`,
an unverified customer-requested `referenced_product_name`,
`explaining_purchase`, `purchase_step`, `last_purchase_topic`,
`last_assistant_response`, and `last_user_transcript`. References are resolved
before independent intent matching. A product reference selects the current
inventory/price record; it never reuses an old price or authorizes a purchase of
an item missing from the fresh inventory. Ambiguous references can be clarified.

Purchase questions and their short follow-ups go to GPT with history and structured
resolution hints. The three explanatory stages are `SCAN_AND_SELECT`,
`VERIFIED_PAYMENT_AND_PICKUP`, and `AUTO_CLOSE_AND_RETURN`; security and timing
questions preserve their relevant context. These track what Vendi explained,
not evidence of customer progress. Explanations have no application-action intent.
Actual transactional YES/NO remains deterministic in `ask_purchase_question()`.

`conversation/knowledge.py` defines the requested paid procedure and the single
`LID_OPEN_SECONDS = 7` knowledge constant. Its compact static facts plus fresh
`ApplicationContext` are sent as `VENDI_CONTEXT` on conversational requests:
QR → mobile shop → select → pay → server verifies → application/Pi instructs
ESP32 → announce payment → open for approximately seven seconds → automatically
close → goodbye/completion → return to vendor operation. QR scanning and reaching
a success page are explicitly **not** dispensing authorization.

This is authoritative voice knowledge for the paid design supplied by the owner.
The web demo lists all products at $1.00 CAD and simulates checkout without charging a card. No payment backend, servo
control, or hardware lifecycle is added by this change. The main application must
implement the paid lifecycle and provide verified, customer-scoped runtime facts.
An explanation never sets `payment_verified` or claims an actual unlock occurred.

An effectively identical adjacent answer triggers one contextual model repair,
with the prior history and a precise correction. Invalid timing/status claims
also use that bounded repair path. If a second attempt still fails, a resolved
purchase question uses the authoritative explanation for that step; otherwise
Vendi asks a focused clarification. Recovery never emits a purchase action.
Updated numeric facts are not mistaken for duplicates. Explicit requests to
repeat are allowed. Ordinary valid conversational turns still make one GPT call.

Greetings and successfully played fallback lines are recorded too; a failed
generation retains the user's question so “try again” still has context.
History and structured state reset on conversation start and actual end (bye,
inactivity, explicit ending, stop/close), never after speech. The voice controller's
existing `agent.reset()` lifecycle handles this. History is in memory only; longer
active conversations send larger prompts and end-of-session data is not persisted.

Run the contextual regression suite and the unchanged live command:

```bash
.venv-vendi/bin/python -m unittest discover -s tests -p 'test_vendi*.py'
CONVERSATION_TIMEOUT=300 .venv-vendi/bin/python -m vendi.voice_demo --live --command wake --mic
```

Ask “How do I buy something?”, “And then?”, “Then what?”, “If I scan the QR code
does it open?”, “Why?”, and “How long does it stay open?”. To test real product
references, connect to the deployed web app or run it locally. Live mode fetches
`VENDIGO_APP_URL` (default `http://127.0.0.1:3000`) on every turn; `--app-url`
overrides this. For the live Vercel Blob inventory, save the public website origin
in `.env.local` and restart the voice process:

```dotenv
VENDIGO_APP_URL=https://vendigo-beryl.vercel.app
```

Use the website address shown under **Domains** in Vercel, rather than the
`vercel.com` project management link. The voice agent reads `/api/state`; the
deployed app accesses the private Blob store with its server-side credentials.
The voice process does not need `BLOB_READ_WRITE_TOKEN` or a local web server.
Both Python Vendi and `npm run voice` use this setting.

Inventory and prices come from the configured web app's store, reread on each
request: private Vercel Blob when hosted, or `data/inventory.json` in local JSON
mode. Admin saves and completed purchases appear in the next spoken answer
without a restart. Conversation
history resolves references such as “How much are they?” and “How many are left
now?”; current quantities and prices always come from the fresh response. An
unreadable store produces “I'm having trouble checking stock right now” instead
of guessing. STT, TTS, microphone gating,
audio priorities, and the existing device command remain unchanged.

**Application integration.** Use one `VendiVoice` instance on one long-lived asyncio
loop. Public methods are asynchronous; synchronous existing controllers need a
bridge onto that loop, not a new `asyncio.run()` for each call.

```python
import asyncio
from vendi import VendiVoice
from vendi.conversation.context import VendigoContext

async def example():
    events = asyncio.Queue()
    voice = VendiVoice(
        context=VendigoContext("http://localhost:3000", robot_id="robot-001"),
        on_event=events.put_nowait,  # Keep callbacks synchronous and nonblocking.
    )
    try:
        await voice.start_roaming()
        # Existing main state machine selects a customer and calls these APIs:
        await voice.say_customer_greeting()
        await voice.ask_purchase_question()  # Configured STT, one deterministic retry.
        # Main application consumes events and decides the next robot state.
        # For voice conversation: await voice.enter_conversation(listen=True)
    finally:
        await voice.close()
```

Other APIs: `stop_roaming()`, `speak(text)`, `personalized_callout(text)`,
`feed_wake_transcript("Hey Vendi")`, `listen_for_wake_word(listen=True)`,
`handle_transcript(text)`, `end_conversation()`, and `stop_all_audio()`.
The application can supply its own `ContextProvider.snapshot()`; snapshots expose
`get_inventory()`, `get_prices()`, and `get_order_status()` helpers.

| Event | Main application's responsibility |
| --- | --- |
| `WAKE_WORD_DETECTED` | Observe the accepted wake trigger. |
| `PAUSE_MOVEMENT_REQUESTED` | Decide how to pause movement using the existing controller. |
| `CONVERSATION_STARTED` | Associate the voice session with the active customer. |
| `PURCHASE_ACCEPTED` | Show the QR/storefront flow; this is consent, not payment. |
| `PURCHASE_DECLINED` | End that customer's offer. |
| `INTENT_REQUESTED` | Validate the current main state and handle only the requested high-level action. |
| `CONVERSATION_ENDED` | Release conversation ownership; inspect its ending reason. |
| `INTERACTION_COMPLETE` | Decide whether to return to roaming or remain in an order flow. |
| `VOICE_ERROR` | Surface safe diagnostics; retry or use the existing UI. |
| `STATE_CHANGED` | Optional status display/telemetry. |
| `LISTENING_READY` | Show that STT is ready and microphone capture is starting. |
| `TRANSCRIPT_RECEIVED` | Display the complete recognized turn for diagnostics. |

Events carry a `session_id`, monotonic timestamp, and payload. Bind that session to
the main controller's customer/order session explicitly. Supported intents are
exactly `SHOW_MENU`, `CHECK_INVENTORY`, `CHECK_PRICE`, `START_PURCHASE`, and
`END_CONVERSATION`; ending is consumed within the voice subsystem. No event confirms
payment or commands a motor/servo. `RETURNING` is only a voice handoff state. After
an interaction Vendi returns to `IDLE`; the main controller must explicitly resume
roaming once appropriate. Stop old `food_robot/vendor.py`, hosted headless voice,
or other playback processes before giving Vendi ownership of the physical audio
devices. The legacy `npm run voice` path remains a separate integration.

**Temporary and unconnected parts.** The wake implementation is an exact whole
transcript matcher with a cooldown, not a production acoustic keyword model. The
CLI manually triggers it. Experimental `--wake-listening` during roaming listens
only in silent gaps; it cannot hear a customer over Vendi's own music/speech, and
recognition of the name depends on the installed model vocabulary. Replace
`WakeWordDetector` with a trained local detector for deployment, retaining the
central microphone gate. False triggers expire via the inactivity timeout without
calling GPT. Physical movement pause, QR UI actions, customer selection, and
verified order/payment context handoff await the main state-machine integration.
Live mode defaults to `VendigoContext`, fetching the web app before every turn.
If unavailable, Vendi says she cannot check stock instead of reusing old facts.

**Failure recovery.** Mic/speaker/STT/provider failures emit `VOICE_ERROR`; an
already-generated error clip is attempted without another ElevenLabs request.
If even the speaker or fallback clip is unavailable, events still return control
without crashing. Provider exceptions are sanitized before logs/events. A customer
gets one fresh microphone/STT attempt after a failure; repeated input failure ends
the session and returns control. Silence does not trigger GPT or repeated error
speech. Inactivity starts after Vendi's greeting/response ends; active provider
requests and speech have their own bounded deadlines. Hesitations such as "um" or
"let me think" keep the microphone turn open without calling GPT. Bye, finished thanks, never
mind, explicit ending, and inactivity produce one `CONVERSATION_ENDED` event.

**Raspberry Pi deployment.** Use Python 3.9+ (a current Python/OpenSSL build is
recommended). For optional offline STT, check Vosk's wheel support for the Pi
OS/architecture. On Raspberry Pi OS, install system audio dependencies:

```bash
sudo apt-get update
sudo apt-get install python3-venv libportaudio2 portaudio19-dev libasound2-dev
python3 -m venv .venv-vendi
source .venv-vendi/bin/activate
python -m pip install -r vendi/requirements.txt
python -m vendi.voice_demo --list-devices
```

Copy the generated `vendi/audio/clips/` fingerprint directory to the Pi, and the
unpacked model if using Vosk; they are intentionally not in Git. Keep identical
`ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL` settings. Set Pi-specific input/output
device names, configure the service user's audio-device permissions, put secrets
in its protected environment file, and run from the repository root. The live
process needs outbound HTTPS for uncached TTS and conversational GPT, and secure
WebSocket access for Scribe STT. Prerecorded phrases and optional Vosk YES/NO STT
work offline. Test speaker/mic wiring, echo guard,
background-noise recognition, and cancellation on the actual Pi before integrating
events. No service is installed or enabled automatically.

Optional tuning is listed in `.env.example`: request/listening timeouts, echo
guard, funny/phrase probabilities, and paths for the clips, cache, or jingle.
No camera, motor, person detector, payment processor, or servo dependency is
required to run any of the voice tests.
