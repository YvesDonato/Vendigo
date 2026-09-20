# Raspberry Pi voice deployment

This configuration is deployed on a Raspberry Pi Zero 2 W running Raspberry Pi OS
as user `admin`, with the repository at `/home/admin/Vendigo` and Python environment
at `/home/admin/Vendigo/.venv`. It uses an SF-558 USB microphone and a USB Audio Device
speaker. Adjust paths, user/group, and ALSA card names when deploying elsewhere.

The system service starts silently at boot and keeps listening after a conversation
ends through “bye” or inactivity. A shopping request or Vendi/Vendigo wake name starts
a conversation. Unrelated speech produces no reply, even during an active session.
After 30 seconds without an accepted interaction, context resets silently. Background
speech never prolongs that window. Classifier failures stay silent and the next
transcript can retry; voice-process, STT/TTS, or device failures cause a clean restart
after five seconds, without a restart-count limit. The Pi needs its own power and internet;
SSH, tmux, and a connected laptop are not required.

## Install

These commands are for a new Pi deployment. On the configured Pi, preserve the
existing `.env.local`, other ALSA settings, dependencies, and unrelated services.

1. Install `python3-venv`, `libportaudio2`, and `alsa-utils` using the Pi's package
   manager. From the repository root, prepare the Python environment:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r vendi/requirements.txt
   mkdir -p .vendi-cache /home/admin/.local/bin
   ```

2. Inspect `arecord -l` and `aplay -l`. Merge the `vendi_mic` and `vendi_speaker`
   definitions from `asound.conf` into `/home/admin/.asoundrc`, updating card names
   if needed. Preserve any other definitions. The aliases convert the microphone's
   48 kHz input and the stereo speaker output to the agent's existing audio formats.

3. Add the variables from [.env.example](.env.example) to the repository's
   `.env.local`, along with your provider keys. Preserve unrelated variables and
   use `chmod 600 .env.local`. Never publish real credentials. The inventory URL
   must point at the public shop's `/api/state` origin, not a Vercel management page.

4. Verify audio and providers, then prepare the speech library. Provider checks and
   clip generation use the configured accounts and credits:

   ```sh
   .venv/bin/python -m vendi.voice_demo --list-devices
   .venv/bin/python -m vendi.voice_demo --check-providers
   .venv/bin/python -m vendi.voice_demo --generate-clips
   .venv/bin/python -m vendi.voice_demo --live --command wake --mic
   ```

5. End the manual conversation before enabling the service. Install the launcher
   and service from the repository root:

   ```sh
   install -m 755 vendi/deploy/vendi /home/admin/.local/bin/vendi
   sudo install -m 644 vendi/deploy/vendi.service /etc/systemd/system/vendi.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now vendi.service
   ```

The service and manual launcher share an exclusive file lock. Stop the service
before running manual audio tests. A conflicting manual launch exits with code 75.

## Operate

```sh
systemctl status vendi
journalctl -u vendi -f
sudo systemctl stop vendi
sudo systemctl start vendi
sudo systemctl restart vendi
```

An explicit stop stays stopped until a start or reboot. To keep Vendi off across
reboots, run `sudo systemctl disable --now vendi`. To restore automatic startup,
run `sudo systemctl enable --now vendi`.

## Voice behavior and validation

- Dollar amounts are spelled out only at the speech boundary: `1.00 CAD` becomes
  “one dollar,” and `2.50 CAD` becomes “two dollars and fifty cents.” The chosen
  voice/model and actual prices are preserved. Normal speed and zero style
  exaggeration are included in the cache fingerprint, so older clips are not reused.
- Unavailable-item responses offer up to two products with positive stock from
  the current verified inventory. Disabled and sold-out items are excluded. One
  available alternative is offered alone; unknown inventory never produces guesses.
- The persistent entry point uses the existing agent's public methods and audio
  scheduler. It adds no motor, payment, lid, or website actions.
- Microphone transcripts use a separate shopping gate with a 0.90 acceptance
  threshold (0.85 for recognized short follow-ups with active history).
  `VENDI_GATE_MODEL` selects its small classifier (default `gpt-4.1-mini`);
  `VENDI_GATE_TIMEOUT` defaults to three seconds. `VENDI_GATE_DEBUG=1` enables
  operator-only classification logs in the journal. See [the voice README](../README.md).
- “Vendigo” stays unchanged in written replies but is sent to TTS as “vend-ee-go.”
  Regenerate the clip library after updating to prepare affected prerecorded lines.

Run the offline regression tests:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_vendi*.py'
systemd-analyze verify vendi/deploy/vendi.service
```

On the deployed Pi, validation also covered live inventory, provider responses,
speaker-to-microphone price pronunciation, consecutive conversations after “bye,”
automatic recovery after a killed process, explicit stop/start, and the shared audio
lock. Boot enablement was verified without rebooting or disrupting other services.
Generated clips, recordings, logs, runtime reports, environments, and credentials
remain local; they are not source files required in Git.
