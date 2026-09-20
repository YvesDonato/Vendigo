Generated ElevenLabs WAV files live here under a voice/settings fingerprint, then
category: `roaming`, `funny`, `greeting`, `question`, `yes`, `no`, `payment`, `goodbye`,
`wake`, `repeat`, and `errors`. The text hash in each filename prevents stale lines.

Run `python3 -m vendi.voice_demo --generate-clips` after configuring an
adult American female `ELEVENLABS_VOICE_ID`. Error clips are generated first. Existing clips
are reused; interrupted downloads are never promoted into the library.

Generated assets are ignored by Git. Copy this directory and its fingerprint
subdirectory to the Pi. Use the same voice/model configuration on both machines.
This is the speech library used by Vendi. No synthetic silence is shipped as a
real voice clip.
