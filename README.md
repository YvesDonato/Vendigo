# OpenClaw IRL

OpenClaw uses one GPT-5.6 Luna agent for typed and spoken conversations. ElevenLabs Speech Engine provides microphone capture, transcription, turn-taking, interruption handling, and speech playback.

Requires Node.js 22.18 or newer.

1. Install dependencies and copy the environment template:

```bash
npm install
cp .env.example .env.local
```

2. Set the required values in `.env.local`:

```bash
OPENAI_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_SPEECH_ENGINE_ID=
```

3. In three terminals, start the app, voice server, and tunnel:

```bash
npm run dev
```

```bash
npm run voice
```

```bash
ngrok http 3001
```

In the ElevenLabs Speech Engine resource, set the upstream WebSocket URL to:

```text
wss://YOUR_PUBLIC_VOICE_SERVER/ws
```

The browser receives only a temporary WebRTC conversation token. API keys remain on the Next.js and voice servers. `VOICE_SERVER_INTERNAL_URL` and `VOICE_SERVER_PORT` are optional when both run locally with the defaults.
