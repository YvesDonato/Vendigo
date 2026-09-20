# Vendigo

**Commerce that comes to you.** A mobile customer shop, a live retail dashboard,
and Vendi's ElevenLabs voice. The existing five products, local SVG illustrations,
white/sky-blue styles, and seven-second pickup flow are preserved.

## Run the web app

Requires Node.js **22.18+** and npm. Run from the repository root:

```bash
npm ci
npm run dev
```

- Customer: **http://localhost:3000/shop** (`/` redirects here).
- Admin: **http://localhost:3000/dashboard**.
- Existing QR links at `/shop/robot-001` still work.

Production demo:

```bash
npm run build
npm start
```

No database, payment provider, or account setup is needed for the web demo.
Keep existing secrets in `.env.local`; `.env.example` documents optional settings.
The shop has no admin link, camera, robot controls, settings, or admin metrics.
The internal dashboard has inventory, purchases, revenue, conversion, and Shop QR.
It deliberately has no authentication; run it in a trusted demo environment.

## Inventory and purchases

Open `/dashboard`, type exact whole-number quantities in **Inventory**, and select
**Save Inventory**. Zero means sold out. Every saved change updates open shops via
the existing event stream (polling remains the fallback). Reloading shows saved
quantities. Changes to an item during its active pickup are rejected. Concurrent
edits include the original quantity so a sale cannot be accidentally overwritten;
use **Reload saved quantities** if the form reports a conflict.

The existing catalog is Coca-Cola, Coke Zero, Sprite, Water, and Chips. All products
cost **$1.00 CAD** (100 cents). Each completed demo purchase adds $1.00 to revenue;
no card is charged. Existing purchase records retain their original amounts.

1. A customer opens `/shop`; a visit is recorded once per tab session.
2. Choose an available product → **Get Item** → **Confirm**.
3. The server checks the product, compartment, and inventory, then verifies the
   existing unlock acknowledgement. It reserves the pickup while it is active.
4. The customer sees a seven-second collection countdown. The server closes the
   compartment even if the customer reloads or closes the browser.
5. After the close acknowledgement, **`completePurchase`** atomically commits the
   purchase record, one-unit decrement, completed order, and analytics state.
6. Recent Purchases, metrics, inventory, and open shops update together. Vendi's
   next question reads the updated state immediately.

`POST /api/purchases` is the customer purchase route. The preserved
`/api/robot/unlock` compatibility route calls the same handler/store function.
`GET /api/orders/[orderId]` only reads status; success-page refreshes never mutate
stock. Order IDs, original request fields, and completed orders persist, so
retries cannot reopen or decrement twice, including after a server restart.

**Recent Purchases** contains actual completed events, newest first, with product,
price, time, and order ID. It shows five by default and up to twenty when expanded;
all records remain in storage for metrics. A fresh installation has zero fake
purchases and zero scans.

## Persistence and analytics

The replaceable `StateStorage` interface and `JsonStateStorage` implementation use
**`data/state.json`** by default. Override with `VENDIGO_DATA_FILE`. The single JSON
file holds the catalog, inventory, purchases (`state.transactions`), orders,
visit identifiers, and analytics. Keep it when restarting or rebuilding.
It is ignored by Git. Back it up when the app is stopped.

Writes use a uniquely named temporary file, flush it to disk, then atomically
rename it over the state file. Purchases and stock are written in the same commit.
Failed writes roll memory back and do not broadcast phantom sales. Corrupt state
fails visibly instead of silently resetting inventory or purchase history.

Use **one long-lived Node process** with a writable local disk. This is intentionally
not a multi-instance/serverless data store. Do not hand-edit the file while the
server runs. If changing catalog names/prices/enabled flags manually, stop the
server, edit `state.products` (prices are integer `priceCents`), and restart.
Normal quantity edits use the dashboard and need no restart.

The browser stores a stable session ID and a successful visit marker in
`sessionStorage`. It retries failed visit registration. The server also persists
visit IDs to deduplicate Strict Mode effects, refreshes, retries, and restarts.
A new tab/browser session counts again. Purchase API calls do not fabricate scans.

- **QR Scans:** recorded shop visits.
- **Purchases:** completed purchase records.
- **Revenue:** sum of recorded purchase amounts in cents.
- **Conversion Rate:** purchases / scans × 100, or 0% when scans are zero.
- **Total Items Remaining:** sum of inventory quantities.

Repeat purchases in one visit can make conversion exceed 100%, by this definition.

## Vendi voice and live inventory

Vendi uses **Matilda**, ElevenLabs' adult American female voice with upbeat alto
presentation, through the existing centralized `ELEVENLABS_VOICE_ID` setting in
`.env.local` / `.env.example`. TTS keeps `eleven_flash_v2_5` and the existing
natural, lightly expressive settings (stability 0.45, similarity 0.8, style 0.15,
speed 1.05). There is no pitch shifting. Cached clips are keyed by voice/model/settings,
so old male audio is not reused. Two self-references now say “snack guide.”

The existing ElevenLabs Scribe STT, “Hey Vendi,” conversation history, GPT-5.6 Luna,
and verified-order/seven-second dispensing knowledge remain in place.

```bash
python3 -m venv .venv-vendi
.venv-vendi/bin/python -m pip install -r vendi/requirements.txt
# Keep the web app running in another terminal, with existing API keys in .env.local.
.venv-vendi/bin/python -m vendi.voice_demo --generate-clips
.venv-vendi/bin/python -m vendi.voice_demo --check-providers
.venv-vendi/bin/python -m vendi.voice_demo --live --command wake --mic
```

For the existing roaming/wake-listening demo:

```bash
.venv-vendi/bin/python -m vendi.voice_demo --live --command roam --wake-listening --duration 300
```

Live `ConversationAgent` defaults to `VendigoContext`. Before **every turn**, it
fetches `/api/state` from `VENDIGO_APP_URL` (default `http://127.0.0.1:3000`);
`--app-url` can override the URL. There is no startup inventory or session cache.
Simple stock/price questions render validated current facts directly; GPT receives
fresh structured context before more complex replies, and stock/price intents
are rendered from that context rather than trusting model-written facts.
Exact remaining quantities, sold-out items, and catalog prices are all shared
with shop/admin. Failure to fetch produces “I'm having trouble checking stock
right now” instead of stale or guessed stock.

The optional legacy `npm run voice` Speech Engine also reads fresh inventory on
each model call and applies the same environment-selected voice to its configured
engine at startup. It still requires `ELEVENLABS_SPEECH_ENGINE_ID`. The normal
Python Vendi path does not require a Speech Engine. Full audio/device and
conversation documentation is in [vendi/README.md](vendi/README.md).

## QR codes and hardware

Open the dashboard using your computer's reachable LAN address, then select
**Shop QR** and download the PNG. Or set `NEXT_PUBLIC_SHOP_ORIGIN` to that address
before starting/building. A QR containing `localhost` only works on that computer.

Hardware source, firmware, camera proxy routes, and legacy robot APIs remain
isolated and preserved. They are not mounted in the active dashboard/shop.
The **existing** lid adapter is retained: `LID_API_URL` and a server-side
`LID_API_KEY` (or local token file) enable it. An empty `LID_API_URL` simulates the
open/close acknowledgements. No new physical integration was added. Voice never
commands the hardware. Active pickups resume their close timer after restart;
an interrupted opening without a recorded acknowledgement is closed and marked
failed, without inventing a purchase. Real hardware must retain its own watchdog
while the website is offline. Preserved operator APIs can recover a failed lock;
there are no robot-control buttons in this demo.

## Verification

```bash
npm run lint
npm run typecheck
npm test
.venv-vendi/bin/python -m unittest discover -s tests -p 'test_vendi_*.py'
python3 -m vendi.voice_demo --smoke
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests use isolated temporary JSON files and ports **3100/3120**, not your
demo inventory. The restart test uses `.venv-vendi/bin/python`; set
`VENDIGO_TEST_PYTHON` to another Python with `vendi/requirements.txt` installed if
needed. Screenshots/traces go to ignored `test-results/`.

Coverage includes manual edits, invalid quantities, sold-out/disabled products,
concurrent shoppers, duplicate orders, revenue/conversion, corrupt/failed storage,
restarting mid-pickup, and actual backend process restarts with Coke 5 → 5 → 4 → 4
and seven persisted visits. Browser tests exercise mobile checkout, reload recovery,
live Recent Purchases/metrics, inventory edits, QR, and absent admin/camera/robot UI.
Voice tests verify fresh admin/purchase changes, exact quantities/prices, sold-out
answers, unavailable storage, model runtime context, STT/TTS contracts, wake words,
conversation history, and the seven-second guide.

Mocked by default: payment ($1 demo purchase; no real charge), physical lid acknowledgements when
no lid URL is set, and offline `--smoke` voice/audio. Cloud speech/model calls require
the existing API keys; microphone/speaker behavior depends on local devices.

The [implementation report](docs/demo-changes.md) lists every changed file and
verification results. The opt-in real provider check is:

```bash
.venv-vendi/bin/python tests/verify_live_voice.py
```

It starts an isolated production server on port 3135 and uses existing cloud API
keys/credits; it does not change operator inventory or actuate physical hardware.
