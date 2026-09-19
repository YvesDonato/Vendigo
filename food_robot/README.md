# Food-vendor audio

The player starts with the existing jingle, repeats it for seven seconds,
stops music, plays one existing ElevenLabs vendor or funny announcement, and
resumes the jingle for another seven seconds. It avoids consecutive repeats of
the same announcement. Each spoken clip plays to completion before music resumes.
Music restarts from the beginning after each announcement.

From `/home/admin/auto-dash`, start it explicitly when ready:

```bash
python3 food_robot/vendor.py
```

Stop with Ctrl+C. SIGTERM also stops the active audio child process. Playback
errors stop the program and remain visible in the terminal.

Defaults use speaker `plughw:0,0` and the existing assets at
`/home/admin/food_robot/audio`. This directory must contain `jingle.wav` and
`voice/vendor*.mp3` or `voice/funny*.mp3`. The prerecorded question, yes, no, and
paid clips are intentionally excluded from announcements. Runtime uses Python's
standard library, `aplay` for WAV, and `mpg123` with ALSA output for MP3. No cloud
API calls are made during playback.

Optional settings:

```bash
python3 food_robot/vendor.py --min-interval 15 --max-interval 25 --speaker plughw:0,0
python3 food_robot/vendor.py --audio-dir /path/to/audio
```

`/home/admin/food_robot/vendor.py` is a launcher for this same player, so
`cd /home/admin/food_robot` followed by `python3 vendor.py` also works. Its
versioned source is `vendor_launcher.py`. The old espeak player is backed up
beside the installed launcher. Stop any already-running old player with Ctrl+C
before restarting; simultaneous players or headless voice sessions can compete
for the same speaker.

This implements the ambient audio portion only. It does not move the car, detect
people, listen to customers, or verify payment. The intended full controller is:

```text
roam + jingle/announcements → detect person → approach → stop audio and motors
→ ask about food → listen for yes/no
  no: farewell → leave → resume roaming/audio
  yes: request QR payment → wait for verified payment → thank customer
       → leave → resume roaming/audio
```

Connecting that controller requires the actual camera/person-detection interface,
motor-control interface with stop feedback, and payment-confirmation source.
