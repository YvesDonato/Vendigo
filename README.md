# Vendigo

**Commerce that comes to you.** A mobile customer shop, a live retail dashboard,
and Vendi's ElevenLabs voice. The seven-product catalog follows the supplied JSON
list, with matching SVG illustrations, the existing white/sky-blue styles, and
the seven-second pickup flow.

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

## Deploy on Vercel

In **Vercel → Vendigo → Storage**, create/connect a **private Blob store** to the
project's Production environment (and Preview if used). Vercel supplies the
server-only `BLOB_READ_WRITE_TOKEN`. Redeploy after connecting it. No database or
separate server is needed. Do not set `VENDIGO_STORAGE=json` on Vercel.

Vercel automatically uses `BlobStateStorage` instead of writing `/var/task/data`.
The authoritative object is **`vendigo/production/state.json`**, containing:

```json
{
  "version": 1,
  "inventory": { "products": [] },
  "purchases": { "purchases": [], "orders": [] },
  "analytics": {
    "qr_scans": 0, "visit_ids": [], "buyer_ids": [], "revision": 0,
    "started_at": "ISO timestamp", "robots": [], "locations": []
  }
}
```

The arrays above illustrate the structure; first use seeds the seven $1 snacks
listed below. Inventory, orders, purchases, and analytics commit as **one JSON
object**, so a sale cannot write stock without its purchase record. Every read
uses Blob `get(..., { access: "private", useCache: false })`. Conditional writes
use the previous ETag (`ifMatch`); conflicting operations reread and retry. A racing
cold start cannot reset existing data. Errors never fall back to `/tmp`, memory,
or a fresh catalog. Preview deployments use `vendigo/preview/state.json` and do
not touch production. `VENDIGO_BLOB_PATH` optionally selects another object.

Use the same `/dashboard` inventory editor and `/shop` customer route. On Vercel,
open pages poll current shared state every second; local development also retains
SSE. The seven-second pickup uses Next's `after()` to keep the request alive after
the response. Durable order leases let subsequent requests recover an interrupted
function without reopening a compartment or recording a duplicate purchase.
Real lid acknowledgements still use `LID_API_URL` / `LID_API_KEY` if configured;
an empty URL retains the demo simulation. Robot movement APIs stay local-only.

The deployed web agent reads the same store directly on each model turn. For
Python Vendi or the standalone voice server running on your laptop, point
`VENDIGO_APP_URL` at the **public Vercel site**, not the separate local shop:

```bash
VENDIGO_APP_URL=https://your-project.vercel.app .venv-vendi/bin/python -m vendi.voice_demo --live --command wake --mic
```

Local `data/*.json` files remain independent and are not uploaded automatically.
Your saved laptop sales/stock are preserved locally. The hosted catalog starts
with the supplied 16-item list; edit hosted stock from the hosted dashboard.
To deliberately use the Blob backend locally, set `VENDIGO_STORAGE=blob` and
the Blob credentials in `.env.local` (use a separate `VENDIGO_BLOB_PATH` for tests).

## Inventory and purchases

Open `/dashboard`, type exact whole-number quantities in **Inventory**, and select
**Save Inventory**. Zero means sold out. Every saved change updates open shops via
the existing event stream. Pages also poll every second for direct JSON edits. Reloading shows saved
quantities. Changes to an item during its active pickup are rejected. Concurrent
edits include the original quantity so a sale cannot be accidentally overwritten;
use **Reload saved quantities** if the form reports a conflict.

The active catalog matches the supplied inventory, totaling **16 items**:

| Product | Starting quantity |
| --- | ---: |
| Rice Krispies Treats Original | 3 |
| KitKat | 3 |
| Hello Panda Chocolate | 2 |
| Kirkland Soft & Chewy Granola Bar | 4 |
| Biscoff Cookies | 2 |
| Smarties | 1 |
| Brookside Acai & Blueberry Dark Chocolate | 1 |

All products cost **$1.00 CAD** (100 cents). The supplied `quantity` values are
stored in each product's `inventory` field; the total is calculated from current
stock. Each completed demo purchase adds $1.00 to revenue;
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
`GET /api/orders/[orderId]` reads durable status; on Vercel it also recovers an
overdue pickup if its original function was interrupted. Success-page refreshes
never create another purchase. Order IDs, original request fields, and completed orders persist, so
retries cannot reopen or decrement twice, including after a server restart.

**Recent Purchases** contains actual completed events, newest first, with product,
price, time, and order ID. It shows ten by default and up to twenty when expanded;
all records remain in storage for metrics. A fresh installation has zero fake
purchases and zero scans.

## Persistence and analytics

The replaceable `StateStorage` interface coordinates `InventoryStore`,
`PurchaseStore`, and `AnalyticsStore`. On first use it creates:

```text
data/
  inventory.json   # authoritative catalog, dollar prices, and stock
  purchases.json   # completed purchase records and durable order IDs/status
  analytics.json   # visit IDs/count and existing runtime metadata
```

Override the directory with `VENDIGO_DATA_DIR`. Keep these files when restarting
or rebuilding; they are ignored by Git. An existing `state.json` is imported once
and preserved as `state.json.bak`, without losing stock, purchases or scans.
The optional legacy `VENDIGO_DATA_FILE` only identifies that import source.

Every file write uses a unique temporary file, `fsync`, and atomic rename. A small
`.pending-transaction.json` recovery journal commits related changes together;
an interrupted replacement is replayed before the next read. A durable purchase
cannot become detached from its stock decrement. Writes that fail before the
commit roll memory back. Corrupt JSON fails visibly instead of resetting data.

For **local JSON mode**, use one long-lived Node process with a writable local
disk. Vercel uses the shared Blob mode described above. Dashboard edits are the easiest way
to manage stock. You can also edit `products[].inventory`, `price` (dollars, up to
two decimals), or `enabled` directly in **`data/inventory.json`** while the server
runs. The next API/voice query reads the saved file; open pages update within
about one second. No startup inventory cache or restart is involved. Save complete,
valid JSON, and avoid simultaneous manual file edits and checkout writes; use the
dashboard when customers are buying. See the [report](docs/demo-changes.md) for
the exact document structures. Back up all three files together while stopped.

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
The API itself rereads `InventoryStore` for each query. Exact remaining quantities,
sold-out items, and catalog prices are all shared
with shop/admin. Conversation history resolves “it,” “they,” and “how many are
left now,” while fresh data supplies the facts. Failure to fetch produces “I'm having trouble checking stock
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

Browser tests use isolated temporary JSON directories and ports **3100/3120**, not your
demo inventory. The restart test uses `.venv-vendi/bin/python`; set
`VENDIGO_TEST_PYTHON` to another Python with `vendi/requirements.txt` installed if
needed. Screenshots/traces go to ignored `test-results/`.

Coverage includes manual edits, invalid quantities, sold-out/disabled products,
concurrent shoppers, duplicate orders, revenue/conversion, corrupt/failed storage,
restarting mid-pickup, and actual backend process restarts with stock 5 → 5 → 4 → 4
and seven persisted visits. Browser tests exercise mobile checkout, reload recovery,
live Recent Purchases/metrics, inventory edits, QR, and absent admin/camera/robot UI.
One running voice session follows Rice Krispies 3 → purchase 2 → admin 9, then direct file
edits to quantity, price and sold-out status, plus recovery from invalid JSON.
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
