# Customer controller and shared audio

The maintained Vendi voice agent lives in [`vendi/`](../vendi/README.md). From the
repository root, start real speech and microphone conversation with:

```bash
.venv-vendi/bin/python -m vendi.voice_demo --live --command wake --mic
```

Vendi also handles roaming announcements and generates its own speech library.
The old standalone audio player, launcher, speech demos, and unused MP3 clips
have been removed.

This directory retains:

- `audio/jingle.wav`: the shared jingle used by Vendi's default configuration.
- `customer_flow.py`: the separate customer/controller simulation.
- `test_customer_flow.py`: the controller's regression tests.
- [CUSTOMER_FLOW.md](CUSTOMER_FLOW.md): the controller's interfaces and integration notes.

Run the controller simulations and tests from the repository root:

```bash
python3 food_robot/customer_flow.py --answer yes
python3 food_robot/customer_flow.py --answer no
python3 -m unittest discover -s food_robot -p 'test_customer_flow.py'
```
