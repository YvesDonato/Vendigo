# LordBot camera steering

The current launcher uses rule-based following for every direction. OpenJEV
is not loaded. YOLO26s + BoT-SORT detect and track people on H100; OWLv2 handles
feet when the selected body is absent. Camera depth still supplies the existing
obstacle checks. The viewer shows “YOLO26s + BoT-SORT / rule-based following”.

## YOLO person tracking (current)

YOLO26s replaces SSDLite; BoT-SORT uses sparse optical flow for camera-motion
compensation and supplies body track IDs. A new body needs score 0.6; an
already-confirmed track can use a current detection down to 0.25. No predicted
or unconfirmed box authorizes movement. The selected body ID takes priority
over a closer bystander. Its ID survives an associated feet detection for up to
two seconds since the last actual body observation; feet do not renew that ID.
After expiry, a replacement body must match the retained feet spatially and by
depth. Full target loss still waits two seconds before choosing another person.
Body/feet transitions can remain ambiguous when feet overlap.

The feet detector is skipped only while the selected body ID appears in the
current frame; a missing body or unrelated bystander restores it immediately.
Long camera gaps reset BoT-SORT IDs and target memory. The current gap is 0.25 m.
The indefinite empty-view forward override has been removed. A lost person
gets the existing brief wait, then a search in one consistent direction for up
to two estimated full rotations. Finding a person ends the search early and
resets the budget for the next loss. Search pauses do not consume turn time;
issued turn leases do, including uncertain acknowledgements so retries cannot
extend the budget. Stop and a new Start reset the run.

The observed calibration was about a quarter turn from 796 ms of powered left
pulses at PWM 255. `--search-rotation-seconds 3.184` therefore allows 6.368 seconds
of cumulative search commands; a remainder below the 80 ms minimum pulse is
discarded. This estimates angle, not encoder/IMU feedback. Battery, surface and
wheel slip can require recalibration. The last pulse still finishes and gets
the existing stopped-camera check before switching to travel.

Search pulses now use a 5 ms settling buffer, reduced from 20 ms, to shorten
pauses while the person is missing. Tracking turns retain 20 ms. Both still
require a newly analyzed image received after confirmed stopped motor output
and the settling buffer. PWM remains at its maximum of 255; the two-turn
powered-time budget is unchanged. Apply `faster-search.patch` after
`search-turns.patch` on the host; no firmware or H100 change is needed.

If no person is found, current learned-depth obstacle points rank left, centre
and right sectors, restricted to the existing permitted movements. Forward is
preferred when its clearance is within 10% of the best sector. This ranks the
currently visible view, not a stored 360-degree map or unseen space. Forward
also requires fresh sonar beyond 25 cm. Reacquisition restores normal following;
missing video, obstacles and Stop keep their existing guards.

All forward suggestions now share the sonar check, including a shoe whose box
is inside the forward steering band but does not cross the image centre.
Previously that case could display straight while firmware blocked it. Invalid
or stale sonar now produces stop with `source=ultrasonic_guard` and retains
`model_direction=straight`. The viewer also expires displayed sonar at 200 ms,
matching the controller, and labels a blocked forward suggestion as paused.
Apply `forward-guard.patch` after `faster-search.patch` on the host. This makes
the blocking reason consistent; it does not repair missing ultrasonic echoes.

`following_intent` is shared by the viewer and motors, with sources `search_scan`
and `clear_path`. Deploy `search-turns.patch` after `empty-forward.patch` to the
host, and its `person_follow.py` / `vlm_reasoner.py` changes to H100. The launcher
supplies the measured full-turn time. Checks are in `test_search_turns.py` and
`search-turns-check.json`. Startup stays disarmed.

## Short turning corrections (current)

Person-following turn corrections use a single full-power command, at most
200 ms and never renewed during that burst. The host then sends Stop, verifies
zero PWM and a disabled driver, waits at least 20 ms, and requires inference on
a frame received after that interval before another movement. It polls the
front sensor while disarmed. Failure to recover within two seconds disables
steering. Forward drive stays continuous. A late acknowledgement, lost reply,
or early change of direction cannot bypass the stopped-camera check.

Turn entry thresholds are 34% and 66% of image width. A left correction
finishes at 38%; a right correction finishes at 62%, allowing forward drive
sooner while retaining a separate entry threshold to reduce boundary jitter.
The same stabilized direction gates the measured forward approach. The viewer
reports “Turning left/right” and “Checking camera after turn”; `/api/state`
adds `steering.turn_phase` (`idle`, `turning`, `stopping`, `observing`). Reading
status never advances that phase.

The 200 ms burst and 20 ms settling buffer are calibration defaults, not a
measured rotation angle or proof that the camera captured a stationary image.
The camera supplies local receipt times, not hardware capture timestamps.
No new firmware, model or dependency is required. Apply `smooth-follow.patch`
after the YOLO and gap patches, then `turn-response.patch` for these faster
settings; deploy `person_follow.py` to both host and H100 and `robot_steering.py`
to the host. The initial burst checks are in `smooth-follow-check.json`; the
latest tuning checks are in `turn-response-check.json`.

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_smooth_follow.py
```

On the user-approved 99-frame clip, both versions retained a target in all
99 frames. YOLO used one body ID in 20 frames and the feet fallback in 79;
SSDLite used feet throughout. Mean processing was 73.6 ms versus 72.7 ms;
YOLO body-target frames had a 50.5 ms median, while feet-target frames had a
78.1 ms median. This is one stationary-robot replay, not a moving-robot or
multi-person tracking validation. See `yolo-follow-check.json`.

The official weights are `ultralytics/assets` release `v8.4.0/yolo26s.pt`,
SHA-256 `646f8bc3fe0a656803d95c294f7852321748cb29d13466a1af8862e2db384a1b`,
verified against the GitHub release digest. Added packages are pinned in
`yolo-requirements.txt`; Torch/CUDA were retained. The worker sets
`YOLO_OFFLINE=true`, `YOLO_AUTOINSTALL=false` and a dedicated `YOLO_CONFIG_DIR`
under its SSD cache, with usage synchronization disabled.

The iPlanner `person_follow.py` change is recorded in `yolo-follow.patch`.
Place `person_botsort.yaml` beside that module on the host and H100 worker.

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_yolo_follow.py
```

## Hybrid following (optional)

Adding the OpenJEV model/head arguments and `--openjev-turns-only` enables hybrid mode: the existing rules
control forward movement, and the trained OpenJEV head chooses permitted
left/right turns. Forward decisions skip OpenJEV inference entirely. A rule
stop for a close person, blocked route or lost-target wait remains a stop;
OpenJEV cannot replace it with a turn or command forward itself.

Before starting a turn or reversing the turn direction, the host sends Stop,
waits 50 ms and checks that both PWM outputs are zero and the motor driver is
disabled. It then re-arms and rechecks the newest decision. This confirms
stopped motor output, not wheel velocity. Renewing the same turn does not
repeat that handoff. A centred target returns directly to rule-based forward.

The 0.5 m gap, ultrasonic limit, camera clearance, freshness checks and Stop
button remain active. Missing ultrasonic readings still block forward motion.
The viewer shows “Rules forward / OpenJEV turns”. Restarting leaves steering
disabled. Host/worker changes are recorded in `hybrid-follow.patch`; apply it
in the iPlanner checkout, with the updated `openjev_follow.py` alongside it.

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_hybrid_follow.py
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_openjev_follow.py
```

## Rule-based person following (current)

Omitting the OpenJEV model, head and turns-only arguments selects the existing
`PersonFollower` rules for every direction. The H100
still detects people/feet and estimates camera depth. Steering turns left or
right when the selected target is outside the central 34–66% of the image,
and drives straight when centred and beyond the following gap. The existing
target association, brief loss hold and search behaviour remain active.

The current gap is **0.25 m**, with a **25 cm ultrasonic front limit**. Turning
uses PWM **255/255**, restored from 200; straight drive remains 255. Actual turn
rate depends on battery and floor friction. The controller accepts the new
distance over Wi-Fi on viewer startup; no firmware flash is needed. Its reboot
default remains 50 cm until the viewer reconnects. Apply `gap-turn.patch` after
`yolo-follow.patch` to update host and worker validation and distance display.
Current-camera obstacle checks can stop the robot before the requested gap.
Missing sensor echoes still block forward drive independently
of the chosen steering policy. Start following runs until Stop; a restart
leaves steering disabled. The viewer identifies the active detector and tracker.
OpenJEV weights and the trained head are retained for hybrid and full-model modes.

## OpenJEV person following (previous mode)

The previous viewer configuration used the H100 OpenJEV 4B
checkpoint with a separately trained steering head. It follows the selected
person or feet at an **estimated 0.5 m gap**, with a measured 50 cm front limit.
Brief detection loss retains the last successfully commanded direction for up
to **1 second** from the last detected frame, with fresh camera clearance and
front-distance readings. It then waits until the existing **2-second**
target-loss interval ends before searching toward the remembered side.
Start following runs until Stop; restarting always leaves steering disabled.

`openjev_follow.py` consumes the existing detector/depth model's structured
tracking state. It does **not** train OpenJEV to recognize feet from pixels.
`train_openjev_follow.py` trains a 163,969-parameter head over frozen OpenJEV
features, following the [published latent-head approach](https://huggingface.co/AlexWortega/openjev/blob/main/modeling_openjev.py).
The original OpenJEV weights remain unchanged. Backboard is no longer called
by the active service; its optional backend is retained below.

The prompt builder normalizes permitted-movement order to the format used in
training: `straight, left, right, stop` for FOLLOW; stop first for HOLD/SEARCH.
The live clearance code supplies stop first, and the trained head is sensitive
to that text difference despite the permission sets being equivalent. On H100,
correcting only this order changed two centred-person cases from stop to straight
and two left-target cases from stop to left. One right-target case still chose
the wrong direction and was stopped by the existing veto. The close-person case
remained stopped. No weights or guards were changed. The CPU regression checks
permission permutations and exact compatibility with every training prompt;
see `prompt-order-check.json` for the GPU comparison. This does not repair
missing ultrasonic echoes, which still pause forward movement.

The experiment has 483 training, 120 validation and 200 test states, with no
identical states across splits. Labels imitate the existing follow rules;
templates and rules are shared. Test action agreement improved from 61.5% to
97%. With the existing current-target direction veto, unnecessary holds fell
from 30 to 5 of 150 synthetic movement cases. The unguarded tuned model still
missed one required stop and chose four wrong turns. The deployed distance,
loss-wait, obstacle and direction checks veto these unsafe/disagreeing actions.
These are synthetic policy tests, **not physical following validation**.
See `openjev-follow-evaluation.json` for the raw results and artifact hashes.

The trained head originated on A100 and is deployed unchanged on H100 at
`/ssd1/userdata/donatoy/openjev-follow-20260919/experiment/head.pt`.
The isolated deployment reuses the existing 4B weights and Torch installation,
with matching Transformers and perception packages. Its viewer arguments are:

```bash
--ssh-host H100 --remote-dir /ssd1/userdata/donatoy/openjev-follow-20260919 \
--camera-jpeg-quality 20 \
--camera-calibration /ssd1/userdata/donatoy/openjev-follow-20260919/robot-trial/camera-code/deberta-camera-calibration.json \
--follow-person --follow-gap 0.5 --follow-distance-scale 1.0 \
--openjev-follow-model /ssd1/userdata/donatoy/openjev-follow-20260919/models/openjev/qwen3.5-4b-nli \
--openjev-follow-head /ssd1/userdata/donatoy/openjev-follow-20260919/experiment/head.pt
```

`start_follow_viewer.py` starts the complete transient `openjev-camera` user
service with the current rule-based 0.25 m gap, drive PWM 255, turn PWM 255 and
the 25 cm front limit. The older OpenJEV experiment requires restoring its
0.5 m gap and 50 cm front limit as well as the two model arguments above. Stop an existing
unit before running it. H100 GPU 2 is selected by UUID; other GPU jobs are untouched.

The same three saved 320×240 camera frames were replayed on both servers, with
15 warmup requests and 60 measured requests each. The 20 requests that ran
OpenJEV and selected straight took **150.5 ms on A100 versus 118.3 ms on H100**
median, or **161.4 versus 128.5 ms** including the laptop round trip. The other
40 requests lost the retained target and skipped OpenJEV through the existing
stop guard. All 60 action decisions matched between servers. These timings
compare the current deployments, not GPU hardware in isolation: A100 shares
its GPU with existing jobs; H100 GPU 2 was idle. Python/NumPy were 3.12/2.3.5 on
A100 and 3.10/2.2.6 on H100. Torch 2.11/cu129, Transformers 5.13, model/head
checksums and the pipeline code match. See `h100-inference-check.json`.

CPU checks (no motors):

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_person_follow.py
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_openjev_follow.py
```

Earlier A100 checks measured model-only inference at about 49 ms median and
live detection plus steering at about 166 ms. Brief video interruptions occurred and can
pause motion: training cannot repair camera/network dropouts. Fresh-frame
checks, Stop, the approximate distance calibration and firmware leases remain.
The original 0.75-second camera connection timeout is retained after the
rollback; loading the trained head does not change camera transport settings.

The camera relay now uses `--camera-jpeg-quality 20`, reapplied before each
stream connection so a camera power cycle retains the bandwidth reduction.
The previous setting was 10; larger ESP32 JPEG values mean smaller images.
A 40-second stationary check on power-bank power received 1,093 frames and
256 decisions, with all 160 sampled connection states healthy. Before the
change, only 36 of 120 samples were connected. This is a short transport check,
not a guarantee against further Wi-Fi or power interruptions. Firmware and
the 500 ms frame deadline are unchanged.

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_camera_quality.py
```

## Front ultrasonic sensor

The reinstalled kit sensor uses **TRIG GPIO13 / ECHO GPIO14**, facing forward.
The motor controller now runs `lordbot-jev-2`, flashed and hash-verified over
USB. Add `--stop-distance-cm 50` to the viewer command for the requested
**0.5 m front limit**. The viewer displays measured front distance separately
from the camera's estimated person distance; an echo may come from another
object and cannot identify the tracked person.

For a selected person centred across the front sensor's axis, the viewer now
uses that measured range for the approach instead of stopping on the camera's
person-distance estimate. With a fresh clear camera path and front reading
above 50 cm, it continuously requests forward motion; at or below 50 cm it
holds position. It can resume when the person moves away. Camera/echo loss
still pauses motion, and Stop still ends the run.

The trained OpenJEV head remains loaded for following, turns and search. During
the centred approach, the host range controller can override its direction,
including a model hold. The API marks this as `source=ultrasonic_approach` and
preserves `model_direction`; the viewer explains the measured-distance action.

The H100 camera calibration now sets `depth_scale=1.75`, with the separate
`--follow-distance-scale` set to `1.0`. This applies the existing measured
camera-distance correction once to both person ranges and obstacle geometry.
Previously person ranges received the correction while the obstacle check
used raw depth. In the reported stopped frame, central pixels were estimated
at 37–40 cm despite a front-sensor reading around 1 m. Replaying the frame with
the shared correction clears the camera veto; the existing measured approach
then selects straight above 50 cm, and stop at or below it. The tuned head
still returns a hold on that frame, which the measured approach already
handles. No firmware, speed, margin, freshness or watchdog limit changed.
This reuses a single-point calibration; it does not validate every obstacle's
distance or physical stopping accuracy. See `straight-calibration-check.json`.

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_depth_calibration.py
```

Only a current selected target overlapping the centre line with a clear
camera obstacle check can authorize this approach. Off-centre targets retain
the existing model and camera rules. During target loss, the brief direction
hold described below can continue a previously authorized movement. This does not
establish that the echo belongs to the person or guarantee an exact physical
stopping distance.

The one-second hold requires a successfully acknowledged movement with a
detected target in the same camera frame. It never starts from search motion
or extends its expiry on repeated misses/renewals. Each new missing-target
frame must still permit that direction through its obstacle check, and the
front sensor must have a valid reading above 50 cm. A stop command, blocked
route, reached gap, stale/missing video or control fault clears the remembered
movement. The API labels these decisions `source=follow_hold` and retains
the underlying `model_direction`. Power remains 255/255; no speed increase or
physical moving test was performed for this update.

Firmware samples every 60 ms in a separate task and blocks forward drive
at or below the cutoff. Missing/invalid echoes and readings older than 200 ms
also block forward drive. Valid readings cover 3–400 cm. The motor watchdog
continues independently, and a clear reading can resume a still-authorized
forward command. This sensor does not measure side clearance or veto turns;
the camera checks, Stop button and 200 ms command leases remain active.

The cutoff is adjustable from 10 to 100 cm through the viewer command or
authenticated `POST /stop-distance`; changing it disarms the controller.
It defaults to 50 cm after reboot. Reseating the sensor cable restored
distance readings after the initial no-echo test, though dropouts were still
observed. A stationary measured-distance check is pending; **distance accuracy
and physical stopping distance are not yet validated**. Motors stayed disabled
during these checks. See `ultrasonic-check.json` for the sampled results.

## TypeSafe Jev via Backboard (optional)

The optional hosted backend uses the actual **TypeSafe Jev** API:
`llm_provider=typesafe`, `model_name=jev-latest`, `POST /threads/messages`.
The resolved model was `jev-1.13.0` in the deployment checks. This is separate
from the earlier OpenJEV checkpoint and the trained DeBERTa classifier.
[Backboard's System One API](https://docs.backboard.io/concepts/system-one)
accepts text and structured state, so the existing A100 detectors/depth model
provide the selected target, estimated range and permitted movement options.
Backboard receives an explicit HOLD, SEARCH or FOLLOW phase and, when searching,
the remembered search side. Missing detections alone must not confuse the
completed wait with a continuing hold. Raw camera images go to the existing
A100 inference process, not Backboard.

`backboard_jev.py` runs on this computer, reads the ignored `backboard.key`
file (mode 0600), and requests a typed `straight/left/right/stop` choice.
The key is never passed to the browser, robot or A100. Enable this backend
by adding the following to the calibrated person-following viewer command:

```bash
--follow-person --follow-gap 0.5 --follow-distance-scale 1.75 \
--backboard-key-file /home/yvesd/Codebases/auto-dash/robot_code/backboard.key
```

There is one API request in flight at a time. Hosted calls took roughly
0.56–0.93 seconds in synthetic checks, so camera processing continues while
Jev runs. A Jev intent expires two seconds after its source image was received.
Every motor decision still requires a camera observation less than 500 ms old,
with the same currently supported direction and valid distance/obstacle checks.
A changed direction, close or lost target, obstacle, expired intent, malformed
reply or API failure produces Stop. There is no local-model fallback pretending
to be Jev. The 0.5 m estimated gap, two-second stationary target-loss wait,
Stop button and 200 ms firmware leases remain active. The viewer shows the
resolved model and the older Jev observation age separately from current video.

Each request uses an independent observation with memory off; no thread history
can authorize movement. API usage is billed by Backboard, including calls made
while the viewer is displaying suggestions with steering disabled.

Checks (no motors):

```bash
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_backboard_jev.py
```

The offline check covers the API contract, single-request behavior, actual
model choices, fresh-frame vetoes, intent expiry and API/credential errors.
The API smoke check used synthetic centred/left/near/missing targets; physical
closed-loop following with this backend has not been validated.

Motor-controller firmware for the ACEBOTT QD106 ESP32 Max 1.0, separate from
the ESP32 camera. The camera firmware and `192.168.8.236:81/stream` stay intact.
The USB controller identified for this session is ESP32-D0WD-V3, 4 MB flash,
MAC `00:70:07:97:50:8c`, serial `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`.

The vendor manual's `Acebott.zip/vehicle.h` defines PWM pins 19/23, clock 18,
enable 16, data 5 and latch 17. The vendor's forward byte 163 moved this
assembled robot backward, confirmed with all four wheels turning at PWM 255.
The corrected forward pattern is its opposite, 92. Left/right rotate remain
83/172 and need a separate physical orientation check. These rotate the
chassis rather than strafing it. `/status` reports the configured `forward_bits`.

## Build and flash

The repurposed lid servo uses GPIO25, as specified by the kit's
`5.2Servo_90.ino`. Authenticated `POST /servo` accepts form field `angle=0..180`.
The servo remains inactive on boot until commanded. Its 50 Hz, 16-bit PWM uses
the kit library's 544–2400 microsecond limits; 180 degrees requests 2400 us.
The installed core allocates this separately from the motor PWM timers.
`/status` reports the requested servo angle, pulse, duty and frequency; these
are electrical output readings, not physical position feedback.

With automatic steering stopped, the hardware check below verifies request
validation, commands 180 degrees, and checks the servo output while confirming
that the motor PWM frequencies and zero wheel outputs are unchanged:

```bash
/tmp/iplanner-openjev-check/bin/python robot_code/test_lid_servo.py
```

The pre-servo flash backup is
`backups/lordbot-00700797508c-before-lid.bin`. The servo-enabled build is in
`build-lid/`; both contain credentials and are excluded from Git.

Copy `LordBotJev/secrets.example.h` to `LordBotJev/secrets.h` and configure the
router Wi-Fi credentials and a random 64-character lowercase hex control
token. Put the same token in `control.token`, with permissions 600. Both
files, build output and firmware backups are ignored by Git. Keep compiled
firmware private too: it contains those credentials.

This session uses Arduino CLI with Espressif core 3.3.12 and its temporary
configuration `/tmp/lordbot-arduino.yaml`. Build from this repository root:

```bash
env PATH="/tmp/iplanner-openjev-check/bin:$PATH" \
  arduino-cli --config-file /tmp/lordbot-arduino.yaml compile \
  --fqbn 'esp32:esp32:esp32:FlashSize=4M,FlashFreq=40,FlashMode=dio,PSRAM=disabled' \
  --build-path "$PWD/robot_code/build" robot_code/LordBotJev
cd robot_code/build
PYTHONPATH=/tmp/lordbot-tools /tmp/iplanner-openjev-check/bin/python -m esptool \
  --port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 --baud 115200 \
  write-flash @flash_args
```

The temporary Python environment and Arduino tools must be recreated if
`/tmp` is cleared. Use Python with NumPy/Pillow/OpenCV for the camera relay;
esptool 5.4 and pyserial are the USB tools used here. The official board index
is `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
The original 4 MB image and its SHA-256 are preserved in
`backups/lordbot-00700797508c-original.bin`. To restore this specific board,
stop the viewer and write that file at address `0x0` using esptool.

Read serial at 115200 after boot for the robot's DHCP address (currently
`192.168.8.100`). Reserve its
MAC in the router if a stable address is needed. Startup always disables
the motors, including after flashing or reconnecting Wi-Fi.

## Viewer and control

The integration lives in `/home/yvesd/codingspace/testML/iPlanner`:

```bash
cd /home/yvesd/codingspace/testML/iPlanner
/tmp/iplanner-openjev-check/bin/python camera_live.py \
  --robot-url http://192.168.8.100 \
  --robot-token-file /home/yvesd/Codebases/auto-dash/robot_code/control.token \
  --stop-distance-cm 50 \
  --drive-speed 255 --turn-speed 255
```

Open `http://127.0.0.1:8770`, then **Start following** (or **Start automatic steering** in navigation mode). There is no run-duration limit; switching tabs or closing the viewer
does not cancel it. **Stop** ends it early. Brief video gaps pause with the
motors disarmed; fresh video within two seconds can resume the same run.
Brief control timeouts and expired leases also pause and establish a new
session, using a fresh camera decision, within that same two-second window.
Longer outages, model failures and other HTTP errors disable the run.
Recovery after those faults requires a new Start action. Without the robot
options the viewer only shows suggestions.

The host defaults to PWM 160; `--drive-speed` and `--turn-speed` allow separate
calibration from 1 to 255, matching the vendor's 8-bit range. The current
`openjev-camera` service uses 255 for both, because the user's subsequent
movement checks required full power to turn all four wheels. Commands require
a private bearer token, an armed session and increasing sequence numbers.
Continuous control uses leases of at most 200 ms. Renewals require fresh
camera decisions. HTTP time is reserved inside the
frame deadline. A separate motor task checks expiry
every 10 ms even while the HTTP server is blocked; expiry disarms the session.
The host limits decisions to 500 ms since local image receipt, including
the HTTP budget. Browser heartbeats are not required.
If a frame has insufficient remaining time to renew movement, the host sends
no renewal while awaiting the next frame. It lets the already-issued lease
expire naturally instead of cutting it short with a zero-PWM command. A new
stop decision still takes priority immediately. At 500 ms it disarms the motors and
waits up to two seconds for a fresh decision before disabling the run.
A stop outside the guarded approach/detection-hold rules holds zero PWM while control stays enabled;
a fresh supported route can resume movement without another click. Explicit
Stop, a long video/control outage, model failure or an unrecoverable command error
disarms control. Camera reads time out after 750 ms and retry after 250 ms.
Sensor capture age is not measured by the ESP32 MJPEG feed.

In generic navigation mode, the viewer uses OpenJEV direction ranking, with no
image-score cutoff by default. The temporary 0.35 cutoff is opt-in via
`--min-route-entailment`; omit it from the service command for original
behavior. Scores are uncalibrated and do not measure clearance. Continuous
steering runs until Stop; a model stop pauses at zero PWM, and a
fresh supported route can resume movement. Explicit Stop or a fault requires
another Start action.

**12 cm is the robot's width from wheel to wheel**, not its stop distance.
The user measured the camera lens at **90 mm (9 cm) above the floor** and
the front-to-back span at **175 mm (17.5 cm)**, with no body overhang beyond
the wheels. This is the overall footprint length; wheel-centre spacing was
not separately measured. `deberta-camera-calibration.json` uses metres and
a vehicle-centred footprint. Camera placement at the front edge, level pitch
and 90-degree horizontal field of view are initial assumptions, not measured
calibration. The file leaves the existing depth scale, speed/braking and
clearance margins at their defaults. Those assumptions need physical checks;
the model's forward-arc descriptions do not certify the robot's pivot turns.
The original 4B model does not use these measurements.

The trained DeBERTa camera adapter reuses the pinned Depth Anything V2 model
and `rgb-clearance-v1` descriptor from training. It vetoes a learned direction
when that direction's estimated stopping envelope is blocked. This remains
an experimental monocular estimate, not a measured obstacle distance.
The isolated A100 adapter is in `robot-trial/camera-code` inside the DeBERTa
deployment. Select it in the host viewer with:

```bash
--remote-dir /raid/userdata/donatoy/openjev-deberta-nav-20260919 \
--deberta-calibration /raid/userdata/donatoy/openjev-deberta-nav-20260919/robot-trial/camera-code/deberta-camera-calibration.json
```

The captured obstructed-view check selected **left**, rather than the original
4B model's **straight**, on all three calls (113–212 ms server inference).
This demonstrates the camera-to-trained-model pipeline; it does not validate
that the left side is physically clear. No motors were commanded by this check.
The earlier 15 cm ultrasonic update was cancelled while the sensor was absent.
The sensor is now reinstalled; the current firmware uses the 50 cm front
cutoff described above. Turn orientation and obstacle avoidance remain
unvalidated. Keep wheels lifted for the exercise.

Authenticated device endpoints:

| Method | Path | Body |
| --- | --- | --- |
| GET | `/status` | None |
| POST | `/arm` | Empty; returns a new session |
| POST | `/drive` | Form fields `session`, `sequence`, `direction`, `speed`, `lease_ms` |
| POST | `/stop` | Empty; disarms |
| POST | `/stop-distance` | Form field `cm`, integer 10–100; disarms |

Directions are `straight`, `left`, `right`, `stop`; leases are 20–200 ms.
All endpoints require `Authorization: Bearer TOKEN`. The token stays on
the host; browser controls use the relay's local same-origin JSON endpoint.

## Checks

```bash
# From auto-dash; add --exercise only with wheels clear of the floor.
/tmp/iplanner-openjev-check/bin/python robot_code/check_robot.py --url http://ROBOT_IP
# From iPlanner; no robot or GPU required.
/tmp/iplanner-openjev-check/bin/python test_robot_steering.py
/tmp/iplanner-openjev-check/bin/python test_camera_live.py
# From auto-dash; no motors or GPU required.
c++ -std=c++11 robot_code/test_range_guard.cpp -o /tmp/test-range-guard
/tmp/test-range-guard
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_ultrasonic_steering.py
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_front_approach.py
PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner \
  /tmp/iplanner-openjev-check/bin/python robot_code/test_follow_hold.py
```

The hardware check validates authentication, command expiry, replay rejection
and control limits. `--exercise` adds brief forward/left/right pulses and
verifies that the watchdog stops PWM during a deliberately stalled HTTP request.
Use `--speed VALUE` to calibrate starting power with lifted wheels; the check
also reads back both hardware PWM duties and the driver's enable pin. HTTP
acknowledgements alone do not establish that a wheel physically turned.

Calibration observations: PWM 80 and 120 produced sound without rotation;
160 produced lifted-wheel movement; a later PWM 200 test turned only one
wheel; PWM 255 turned all four. The vendor's forward pattern 163 drove
backward. Firmware using pattern 92 was flashed with hash verification,
reported `forward_bits=92`, passed the non-moving checks, and the user
confirmed forward movement during a one-second PWM 255 test.

Before the collision adjustment, a combined test used the camera on a power bank, the real remote
OpenJEV model and the corrected motor firmware. Over 3.03 seconds, 19 sampled
fresh frame IDs drove PWM 255; the last observed command sequence was 58.
Sampled decision ages were 139–291 ms. Both hardware PWM registers read full
duty, and the controller ended disarmed with zero PWM and its driver disabled.

That test exercised forward output only. Turn orientation and obstacle
avoidance remain unvalidated. Earlier tests observed OpenJEV choosing straight
for an obstructed view, and network delays exceeding the 500 ms freshness
cutoff. Keep testing supervised with wheels lifted; the cutoff remains active
and a video outage lasting beyond the recovery window requires a new Start action.


## Follow one centred target

The live viewer now runs person-following mode. **Start following** enables
continuous control, with no 30-second limit; **Stop** disarms it. Switching or
closing browser tabs does not cancel the run. It uses the official
[TorchVision SSDLite320 MobileNetV3 COCO detector](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html)
and existing RGB depth model, plus
[OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) for feet,
worn shoes and socks in partial views. This mode bypasses the DeBERTa classifier.

People scoring at least 0.6 are ranked by estimated range inside their detected
body boxes. Foot detections use their own 0.25 score threshold; scores from the
two detectors are not comparable probabilities. Feet inside detected body boxes
are deduplicated. It initially selects the detection closest to the image centre,
then retains that target using box overlap and approximate range. A closer or
more central bystander does not automatically replace it. The selected detection
is highlighted green, and it turns to keep that target centred while following.
This is geometric association, not identity recognition; crossing/occluding
people can still confuse it.

When the selected target disappears, its identity remains reserved for
**2 seconds**, starting with the first missing detection, even when bystanders
remain visible. With the ultrasonic integration, the host can continue the
last driving direction for up to **1 second from its last detected frame**,
subject to the current camera and range checks above, then wait still. Repeated
misses cannot extend either interval. Reacquisition resumes following immediately.
After the wait, it may select a new central target or, if nobody is visible,
search toward the last clear side (left initially). Centred detections preserve
that search side; small centre-line jitter cannot reverse it.
Close people, visible estimated obstacles, unusable camera images and connection
failures can still stop motion. Detection-box size alone does not indicate
distance: a centred target beyond the gap gets a forward command immediately,
even when a seated or cropped person occupies much of the image.

Add `--follow-person --follow-gap 0.5` to the calibrated DeBERTa camera command
above. The gap is an estimate in metres, adjustable from 0.5 to 3; physical
distance accuracy and turn orientation are not yet validated. The live service
uses the requested **0.5 metre** gap; the CLI default remains 1 metre. Footwear may still be missed or confused
with unworn shoes; this does not establish identity or guarantee clearance.
Camera-only following does not require an ultrasonic sensor; the current
deployment additionally enforces the measured front limit described above.

Following uses the median of up to three target-distance readings from the last
0.4 seconds. One isolated low reading near the gap no longer stops an established
track. With the current 0.5 m gap, any estimate at or below 0.5 m bypasses
smoothing to stop immediately. New/non-overlapping targets,
detection loss and expired history clear the filter. There is no extra 10 cm
or 0.3-second resume wait;
following resumes when the filtered range clears the gap. Obstacle vetoes,
camera freshness, Stop and the firmware watchdog remain active.

The original target-distance correction used `--follow-distance-scale 1.75`: the user measured
1.5 m to the nearest feet while 35 fresh estimates had a median of 0.859 m
(median absolute deviation 0.047 m). The current H100 deployment instead applies
that factor in the shared camera `depth_scale` and sets the target-only scale
to `1.0`, preserving person/feet distances while correcting obstacle geometry
consistently. The following gap is unchanged. This is a single-point adjustment,
not validation at other distances or in other scenes; original evidence is in
`person-distance-calibration-check.json`.
The viewer shows the current Stop reason above the video and polls every 100 ms
to reduce stale-display intervals; motor freshness limits remain 500 ms.
Start stays available while the camera/model/controller are ready; the host
checks its newest decision when clicked. Expiry appears beside the frame age,
while the last model suggestion keeps a steady label and colour.

OWLv2 is pinned to revision `cfd3195ba4ea9592eec887ded089f4c08eff231d` and loaded
offline from the deployment's Hugging Face cache using its existing Transformers
and TorchVision packages. To provision that cache, temporarily enable Hub access
and use `snapshot_download("google/owlv2-base-patch16-ensemble", revision="cfd3195ba4ea9592eec887ded089f4c08eff231d", allow_patterns=["*.json", "*.txt", "*.safetensors"])`.
The GPU check detected socks/shoes in a feet-only camera crop missed by SSDlite,
preserved the existing person detection, and rejected the bag/floor fixtures.
Native 320×240 camera inference took about 160–165 ms in that check. Cropped
fixtures exercise detection only; their changed framing is not range calibration.

The checkpoint is `ssdlite320_mobilenet_v3_large_coco-a79551df.pth`, SHA-256
`a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`.
It is stored in the existing A100 deployment's `models` directory.
`person_follow.py` lives alongside the iPlanner host/backend code. Check it with
`PYTHONPATH=/home/yvesd/codingspace/testML/iPlanner /tmp/iplanner-openjev-check/bin/python robot_code/test_person_follow.py`.
The fake-controller check advances beyond 30 seconds and verifies continued
control, Stop, lost video, expired leases and bounded reconnects without motors.
