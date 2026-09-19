# Customer camera interaction

`customer_flow.py` implements and simulates the conversation controller. It is
not connected to hardware yet. The existing `vendor.py` and `interaction.py`
are unchanged; running the existing vendor command still only plays audio.

Run the simulations without a camera, microphone, speaker, or motors:

```sh
python3 customer_flow.py --answer yes
python3 customer_flow.py --answer no
python3 -m unittest -v test_customer_flow.py
```

The flow is:

1. The second ESP32 camera supplies images to a person detector and tracker.
   A selected customer is identified by a temporary tracker ID. Stop the jingle
   and robot motion, then invite them over using a visible shirt color when
   confidently available, for example “Hello, person in the white shirt!”
2. Wait for a fresh distance measurement associated with that customer. At
   1.5 meters or closer, ask “Would you like to buy some food?” and listen.
3. For **no**, say “No problem! Have a nice day.”
4. For **yes**, display the order QR code and ask them to scan it to place an
   order. Wait for confirmation from the order system before thanking them.
5. Request departure, restart the jingle after the goodbye finishes, and wait
   for navigation to confirm departure before selecting another customer.

The bot also leaves after no approach (20 seconds), no understood answer
(12 seconds), or no confirmed order (180 seconds). These are configurable.
A tracker ID has a 120-second cooldown to avoid immediately calling again.
This does not recognize the same person after the tracker assigns a new ID.

## Connections still required

- **Second camera:** its stream URL, a person detector/tracker, and confident
  clothing color output. Call `customer_seen(id, shirt_color)` for a selected
  candidate. Use `None` for an uncertain color. No facial identity or sensitive
  personal attribute inference is needed.
- **Distance:** depth/range hardware and calibration to associate range with the
  selected person. A single general obstacle reading is not sufficient to
  identify which customer is near. Call `distance(id, meters, observed_at)`;
  timestamps use the controller's monotonic clock. Reject invalid or stale
  readings in the adapter too. No range is estimated from image size here.
- **Speech/audio:** implement `Ports` using the chosen speech voice and existing
  audio player. One component must own audio playback, so the standalone vendor
  loop cannot keep playing during conversations. `speak` must finish playback
  before returning. `listen(session_id)` starts bounded asynchronous listening;
  recognized yes/no results call `answer(session_id, result)` on the controller's
  event loop. The existing blocking speech demo is not yet this adapter.
- **Ordering:** `show_order_qr(session_id)` must show a real checkout URL tied to
  the session. Only the trusted order backend calls `order_completed(session_id)`
  after an order is accepted. Seeing a QR scan or hearing “done” is insufficient.
  Timed-out sessions do not trigger a thank-you; their orders must still be
  handled by the backend. Departure here follows order confirmation, so any
  food dispensing/handoff requirement must be integrated before departure.
- **Movement:** `stop_motion()` and `leave(session_id)` must use the robot's
  navigation controller with obstacle handling. The bot remains stopped while
  talking and ordering. `leave` requests navigation asynchronously; its success
  event calls `departure_completed(session_id)`. No motor commands exist here.

Serialize all controller events in one event loop and call `tick()` regularly
(for example every 100 ms) even without sensor events. Commands must raise on
failure; the application must stop processing events, report the fault, and
call `shutdown()` in `finally`. The controller does not retry failed hardware
commands. Start the normal roaming/jingle behavior in the integrating application.
The print-only simulation acknowledges events immediately and is not a live
integration or a sensor test.
