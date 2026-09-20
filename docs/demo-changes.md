# Demo implementation report

Implemented and verified on 2026-09-20, including the follow-up requiring three
JSON files and live manual file edits. See [README](../README.md) for setup and usage.

**Latest supplied catalog:** the active `data/inventory.json` and fresh-install
seed now contain **Rice Krispies Treats Original (3), KitKat (3), Hello Panda
Chocolate (2), Kirkland Soft & Chewy Granola Bar (4), Biscoff Cookies (2), Smarties
(1), and Brookside Acai & Blueberry Dark Chocolate (1)**. All prices remain **$1
CAD**, totaling **16 items**. These exact names, IDs and quantities replace all
earlier example catalogs described in the historical notes below. The supplied
`quantity` values map to the existing `inventory` field. Purchase history and
analytics were retained. Seven matching SVG product illustrations were added;
the storefront now shows “Snacks & treats.” and hides empty category filters.

The catalog follow-up changes `src/lib/demo-data.ts`,
`src/components/storefront/storefront.tsx`, `src/app/globals.css`, the active
`data/inventory.json`, `README.md`, this report, and the backend/browser/live-voice
integration test fixtures. New images are `public/products/rice-krispies-original.svg`,
`kitkat.svg`, `hello-panda-chocolate.svg`, `kirkland-granola-bar.svg`,
`biscoff-cookies.svg`, `smarties.svg`, and `brookside-acai-blueberry.svg`.
Product-name matching in `vendi/conversation/intents.py` also treats `&` and
spoken “and” identically; `tests/test_vendi_live_inventory.py` covers both forms.
All seven live quantity and $1 price answers were verified against the local app.
The updated backend suite passes 28 tests and the voice suite passes 85 tests;
TypeScript, lint, the production build, the mobile catalog check, and all seven
production browser tests (including checkout and backend restarts) pass.

## Changed files

These are the files edited/added for this task, including changes inside the
pre-existing, untracked `vendi/` work. Other pre-existing voice tests/files were
preserved.

| Area | Files |
| --- | --- |
| Persistence and purchases | `src/lib/server/storage.ts` (new), `src/lib/server/store.ts`, `src/lib/server/runtime.ts`, `src/lib/demo-data.ts`, `src/lib/metrics.ts` (new), `src/types/index.ts` |
| API and routing | `src/app/api/inventory/route.ts` (new), `src/app/api/purchases/route.ts` (new), `src/app/shop/page.tsx` (new), `src/app/page.tsx` |
| Shop | `src/components/storefront/storefront.tsx`, `src/components/storefront/purchase.tsx` |
| Dashboard | `src/components/dashboard/dashboard.tsx`, `inventory.tsx`, `analytics.tsx`, `recent-sales.tsx`, `qr-code.tsx`, `src/app/globals.css` |
| Live Python voice | `vendi/config.py`, `vendi/conversation/agent.py`, `context.py`, `intents.py`, `guardrails.py`, `vendi/voice_demo.py`, `vendi/audio/phrase_manager.py` |
| Preserved legacy voice integration | `src/agent/live-inventory.ts` (new), `src/agent/run-agent.ts`, `voice-server/server.mts`, `generate_voice.mjs` |
| Configuration and documentation | `.env.local` (ignored; voice ID changed, secrets preserved), `.env.example`, `.gitignore`, `package.json`, `README.md`, `vendi/README.md`, `vendi/audio/clips/README.md`, `docs/demo-changes.md` (new) |
| Tests | `tests/backend.test.ts`, `tests/storage.test.ts` (new), `tests/test_vendi_voice.py`, `tests/test_vendi_live_inventory.py` (new), `tests/verify_live_voice.py` (new), `tests/e2e/demo.spec.ts`, `camera.spec.ts`, `restart.spec.ts` (new), `playwright.config.ts` |

No product images, low-level robot/lid adapters, hardware firmware, STT engine,
wake-word engine, or GPT model selection were replaced.

## Behavior

- **Female voice:** Matilda, adult American female/upbeat alto. Selected centrally
  with `ELEVENLABS_VOICE_ID=XrExE9yKIg1WjnnlVkGX`. The existing ElevenLabs Flash
  TTS model/settings and personality remain; no artificial pitch shift.
- **Persistence:** `data/inventory.json`, `data/purchases.json`, and
  `data/analytics.json`, configurable with `VENDIGO_DATA_DIR`. The previous
  `state.json` is imported once and kept as `state.json.bak`. A recovery journal
  coordinates atomic file replacements for inventory, purchases and analytics.
- **Manual inventory:** `/dashboard` → Inventory → type integer quantities →
  Save Inventory. An open shop updates through the existing event stream.
  Direct JSON edits are read on every request and polled by pages every second.
- **Decrement:** canonical `completePurchase` runs once after the existing
  seven-second pickup has successfully relocked. Stock cannot go below zero.
- **Duplicates:** durable order IDs plus matching original request fields and a
  purchase-record check. Reload/retry/restart cannot repeat the decrement.
- **QR scans:** one successful visit registration per tab session, with browser
  session storage and durable server deduplication. Purchases do not add scans.
- **Recent Purchases:** actual persistent completed records, newest first, with
  product, price, timestamp and order ID; ten shown, expandable to twenty.
- **Routes:** `/shop` for customers; `/dashboard` for operators. Existing
  `/shop/robot-001` links still work. The shop has no admin navigation.
- **Live Vendi facts:** before every turn, `VendigoContext` fetches `/api/state`.
  Direct answers and structured GPT runtime context use that current snapshot.
  Unknown/unavailable inventory produces an explicit failure response, never a
  guessed or cached stock value. Legacy Node voice also fetches fresh state.

## Verification results

- `npm test`: **28 passed**, including durable writes, duplicate/concurrent orders,
  stock validation, revenue, scans, conversion, restart recovery and hardware
  preservation. All seven original camera firmware file hashes match.
- Python voice suite: **84 passed**, including the existing speech/wake/history/
  seven-second guide tests and new fresh inventory/price/sold-out tests.
- Playwright: **7 passed** against production, covering phone/desktop layouts,
  separate customer/admin sessions, successful pickup, reload recovery, server
  timer after disconnect, live inventory editing, QR, API validation and absent
  camera/robot/admin shop UI.
- Actual backend stop/start: **Coke 5 → restart 5 → purchase 4 → restart 4**;
  purchase record and seven QR visits survived; duplicate replay changed nothing.
  Vendi queried the restarted server and answered **4 left**. The extended browser
  test then ran one Vendi session through **3 → purchase 2 → admin 9**, direct
  file edits to stock and prices, sold-out state, and unreadable-file recovery.
- `npm run lint`, `npm run typecheck`, `npm run build`, `git diff --check`: passed.
- `python3 -m vendi.voice_demo --smoke`: all seven offline paths passed.
- Generated all **34** reusable ElevenLabs phrase clips for the female voice,
  including cached error fallbacks, greetings and wake responses.
- `VOICE_SERVER_PORT=3140 npm run voice`: preserved ElevenLabs Speech Engine
  started successfully with the configured female voice; stopped after verification.
- Opt-in real providers (`.venv-vendi/bin/python tests/verify_live_voice.py`):
  passed against its own isolated production shop with existing API keys. Vendi
  answered **3 left**, then **2 left** immediately after purchase. Actual
  **GPT-5.6 Luna** returned **2 left**, then **9 left** after an admin restock in the
  same conversation, and the seven-second explanation. An admin change to zero
  produced **sold out**. Catalog pricing was **1.00 CAD**.
  **ElevenLabs TTS** generated `test-results/vendi-matilda.wav`, and actual
  **Scribe STT** transcribed the generated sample successfully. This verifies the
  providers; it does not test a physical microphone/speaker or subjective voice preference.

## Remaining demo behavior and limits

All products now cost $1.00 CAD. Completed demo purchases add $1.00 to revenue;
existing records keep their original amounts. Other prices are also tested with a temporary catalog. No Stripe charge/payment system was added.
Lid acknowledgements are simulated when `LID_API_URL` is empty; hardware source and
the existing opt-in adapter remain. Physical hardware was not actuated during
verification. The JSON store expects one server process and a persistent writable
disk. The internal dashboard remains unauthenticated for the hackathon.

## Follow-up: $1 pricing

All five seed products and the existing persistent catalog were updated to
100 cents each. Browser checkout/revenue assertions and the live Vendi price
check now expect $1.00 CAD. Inventory quantities and historical purchases were preserved.

Follow-up validation: 23 backend tests and the production build passed. Both
pricing-focused browser tests passed: mobile checkout/revenue and restart/Vendi
price consistency.

## Files changed in the three-file/live-inventory follow-up

The earlier table records the original simplification. This follow-up preserves
that work and changes these existing files:

| Area | Exact files |
| --- | --- |
| Storage and types | `src/lib/server/storage.ts`, `src/lib/server/store.ts`, `src/lib/server/runtime.ts`, `src/types/index.ts` |
| Request-only store initialization and readable errors | `src/app/api/events/route.ts`, `src/app/api/state/route.ts`, `src/app/api/scans/route.ts`, `src/app/api/inventory/route.ts`, `src/app/api/orders/[orderId]/route.ts`, `src/app/api/robot/command/route.ts`, `src/app/api/robot/unlock/route.ts`, `src/app/shop/[robotId]/page.tsx` |
| Live shop and dashboard | `src/hooks/use-live-state.ts`, `src/components/storefront/storefront.tsx`, `src/components/storefront/purchase.tsx`, `src/components/dashboard/analytics.tsx`, `src/components/dashboard/recent-sales.tsx`, `src/app/globals.css` |
| Conversation references | `vendi/conversation/session.py`, `vendi/conversation/intents.py` |
| Tests | `tests/storage.test.ts`, `tests/e2e/restart.spec.ts`, `tests/test_vendi_live_inventory.py`, `tests/verify_live_voice.py`, `playwright.config.ts` |
| Configuration and docs | `.env.example`, `README.md`, `vendi/README.md`, `docs/demo-changes.md` |

Starting `next dev` also regenerates `next-env.d.ts` to reference its development
route types; this is generated framework output, not a hand-written application change.

New source/test files:

- `src/lib/server/inventory-store.ts`
- `src/lib/server/purchase-store.ts`
- `src/lib/server/analytics-store.ts`
- `src/lib/server/json-file.ts`
- `tests/verify_live_inventory.py`

New local runtime files (ignored by Git): `data/inventory.json`,
`data/purchases.json`, `data/analytics.json`. The old saved file was retained as
`data/state.json.bak`. The import preserved all five stock quantities, their $1
prices, and the existing two QR visits; it did not add example purchases.
`.pending-transaction.json` exists only while committing/recovering a write.
Generated verification audio and screenshots are under ignored `test-results/`;
the female voice sample is also retained at `.vendi-cache/review/vendi-matilda.wav`.

## Exact JSON structures

`inventory.json` has one root `products` array. Every entry uses this structure
(this is the existing Coke entry; the same fields apply to the other four):

```json
{
  "products": [
    {
      "id": "coke",
      "name": "Coca-Cola",
      "description": "The original. Ice cold.",
      "image": "/products/coke.svg",
      "color": "#da433c",
      "category": "drinks",
      "enabled": true,
      "price": 1,
      "inventory": 8,
      "robotId": "robot-001",
      "compartmentId": 1,
      "capacity": 12
    }
  ]
}
```

The real file contains **Coca-Cola**, **Coke Zero**, **Sprite**, **Water**, and
**Chips**, with their original IDs and SVG images. Initial stock is 8, 4, 7, 9,
and 6 respectively. All five prices remain **$1.00 CAD**. `price` is a dollar
amount with at most two decimals; the API and purchase calculations use integer
cents. `inventory` must be a nonnegative safe integer. Compartment mappings are
preserved for the existing checkout adapter, and are not controls in the UI.

`purchases.json` starts as `{"purchases": [], "orders": []}`. Here is the exact
shape after an illustrative completed order (this example is not inserted into
the running demo):

```json
{
  "purchases": [
    {
      "order_id": "demo-example",
      "product_id": "coke",
      "product_name": "Coca-Cola",
      "price": 1,
      "timestamp": "2026-09-20T05:30:07.000Z",
      "robot_id": "robot-001",
      "location_id": "hacking"
    }
  ],
  "orders": [
    {
      "id": "demo-example",
      "robotId": "robot-001",
      "productId": "coke",
      "productName": "Coca-Cola",
      "amountCents": 100,
      "compartmentId": 1,
      "sessionId": "example-session",
      "locationId": "hacking",
      "status": "completed",
      "closesAt": 1789882207000,
      "error": null,
      "openedAt": 1789882200000
    }
  ]
}
```

`orders` retains in-progress, failed and completed IDs/status so callbacks and
restarts cannot sell the same order twice. An opening order has `closesAt: null`
and no `openedAt` until acknowledged. Older imported orders can lack the newly
captured `productName`/`amountCents` fields. Completed purchase records preserve
the price agreed when checkout was confirmed, even if a catalog edit happens
during the seven-second pickup.

`analytics.json` contains the visit counter and IDs, plus the minimum existing
runtime metadata needed by the preserved checkout:

```json
{
  "qr_scans": 0,
  "visit_ids": [],
  "buyer_ids": [],
  "revision": 0,
  "started_at": "2026-09-20T05:30:00.000Z",
  "robots": [
    {
      "id": "robot-001",
      "name": "Vendigo #1",
      "status": "available",
      "locationId": "hacking",
      "battery": 74
    }
  ],
  "locations": [
    { "id": "hacking", "name": "Main Hacking Area", "shortName": "Hacking area", "demand": "high" },
    { "id": "sponsors", "name": "Sponsor Area", "shortName": "Sponsor area", "demand": "high" },
    { "id": "entrance", "name": "Entrance", "shortName": "Entrance", "demand": "medium" },
    { "id": "lounge", "name": "Lounge", "shortName": "Lounge", "demand": "low" }
  ]
}
```

This shows a fresh installation. Existing counters are retained. Visit/buyer IDs
are stored as `robot-001:<session-id>`. Revenue and purchase totals are computed
from `purchases`, not separately duplicated in analytics. The preserved hardware
metadata is not displayed as fake dashboard metrics.

## Write safety and consistency

`InventoryStore`, `PurchaseStore` and `AnalyticsStore` validate their documents.
`JsonStateStorage` coordinates mutations through a small recovery journal:

1. Validate all three prospective documents.
2. Write the journal to a unique temporary file, flush it, and atomically rename.
3. Replace each data file using the same temp-file/flush/rename method.
4. Remove the journal once all three replacements finish.

If the process stops between replacements, the next read replays the committed
journal before exposing state. A test injects failure after inventory is replaced
but before purchases are replaced, then proves recovery retains exactly one sale
and one decrement. Failures before committing roll in-memory changes back.
Corrupt/missing files produce an error instead of silently reseeding. A malformed
file does not stop an already open pickup from relocking, and is not overwritten
with an old inventory copy. Next.js builds never initialize the store or write data.

Reads are fresh for every query and every mutation. Dashboard/API mutations push
SSE updates; open pages also poll once per second to detect external file edits.
A runtime instance identifier lets already-open pages accept state after a server
restart even if in-memory revision numbers reset. The intended deployment is a
single Node server on a persistent local disk. Simultaneous external text-editor
writes and checkout writes are not a multi-process transaction protocol; prefer
the dashboard during active sales.

## Operator and customer flow

- **Admin:** `http://127.0.0.1:3000/dashboard` → Inventory → type stock →
  **Save Inventory**. Integer quantities of zero or more are validated in the form
  and backend. Drafts include their original quantity to reject conflicting edits.
- **Customer:** `http://127.0.0.1:3000/shop`. Existing `/shop/robot-001` links work.
  Product cards show current price/stock; sold-out products cannot be selected.
  The confirmation also disables when a selected product becomes unavailable.
- **Purchase:** the existing demo Confirm/unlock/seven-second/close flow remains.
  Only successful completion calls `completePurchase`, which checks saved order
  identity, validates remaining stock, adds a purchase and decrements one unit.
  `GET /api/orders/[orderId]` is read-only. Replaying a completed order returns its
  result without reopening or changing stock.
- **Recent Purchases:** reads completed records from the same store, newest first,
  with product, amount, time and order ID. Ten rows are shown, expandable to twenty;
  the full history remains for metrics. No placeholder purchase rows are inserted.
- **QR scans:** `/shop` registers `POST /api/scans` with a tab/session ID and sets
  `vendigo_shop_visit_recorded-robot-001` in `sessionStorage` after success. The
  server also deduplicates IDs durably. Renders, retries and same-session refreshes
  do not add scans; a separate session does.
- **Metrics:** purchases = completed record count; revenue = their amount sum;
  conversion = purchases/scans × 100, or 0% with zero scans; items remaining =
  current stock sum. Repeat purchases in one visit can make conversion exceed 100%.
  Revenue charts now use actual event times and a useful scale for $1 sales, with
  an honest empty state before the first purchase.

The camera preview/panel/status/buttons and the entire Robot Controls section
(movement, stop/resume, return-to-base, manual compartment controls) are absent
from the active dashboard/shop. The shop also has no SaaS/admin links, inventory
editor, revenue, purchases list or internal operational status. Hardware source,
camera firmware/proxy APIs and existing controller adapters are preserved.

## Voice configuration and fresh facts

The central configuration is:

```env
ELEVENLABS_VOICE_ID=XrExE9yKIg1WjnnlVkGX
ELEVENLABS_MODEL=eleven_flash_v2_5
OPENAI_MODEL=gpt-5.6-luna
VENDIGO_APP_URL=http://127.0.0.1:3000
```

This selects **Matilda**, the adult female voice already configured in the previous
update. The current local configuration was verified. Voice ID selection stays
in environment/config, with the existing natural/lightly expressive settings and
voice-specific clip cache. STT, Hey Vendi, memory, GPT model selection and the
seven-second procedural knowledge remain intact.

Before every response, `VendigoContext` fetches `/api/state`, whose store reloads
`inventory.json`. This includes follow-ups such as “How much are they?” and “How
many are left now?” History identifies the product; fresh state supplies quantity,
availability and price. Simple factual answers are rendered from validated facts.
More complex GPT calls receive the fresh structured context before generation,
and stock/price answer fields are rendered from that context. Zero quantity is
sold out; disabled products are unavailable. If the store cannot be read, Vendi
says “I'm having trouble checking stock right now” instead of using old data.
The standalone legacy voice server also fetches the live API per model call.
The Python voice agent has no hardware command execution capability.

## Exact run and verification commands

From the repository root, start the integrated frontend/backend:

```bash
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

For a production demo, use `npm run build` followed by `npm start` instead.
Keep the existing API keys in `.env.local`. In another terminal:

```bash
python3 -m venv .venv-vendi
.venv-vendi/bin/python -m pip install -r vendi/requirements.txt
.venv-vendi/bin/python -m vendi.voice_demo --generate-clips
.venv-vendi/bin/python -m vendi.voice_demo --check-providers
.venv-vendi/bin/python -m vendi.voice_demo --live --command wake --mic
```

For continuous roaming with the Hey Vendi wake listener:

```bash
.venv-vendi/bin/python -m vendi.voice_demo --live --command roam --wake-listening --duration 300
```

The optional preserved Speech Engine server uses `npm run voice` and requires
`ELEVENLABS_SPEECH_ENGINE_ID`; it is not required by the Python voice demo.

Checks executed for this update:

```bash
npm test
npm run typecheck
npm run lint
.venv-vendi/bin/python -m unittest discover -s tests -p 'test_vendi_*.py'
python3 -m vendi.voice_demo --smoke
npm run build
npm run test:e2e
.venv-vendi/bin/python tests/verify_live_voice.py
git diff --check
```

Results: 28 backend tests, 84 Python tests, 7 production browser tests, the build,
TypeScript, lint, seven offline voice paths, and actual ElevenLabs/GPT checks
passed. Browser tests use temporary data directories on ports 3100/3120. The real
provider check uses port 3135 and existing API credentials. Test purchases never
altered the operator's catalog or purchase history. The hardware preservation
test still confirms the seven original camera firmware files are unchanged.
The restart test additionally passed on its own with automatic forced termination
when open SSE connections delay graceful shutdown. A final mobile-browser check
of the actual `http://127.0.0.1:3000/shop` and `/dashboard` passed with no browser
errors; the local dev server was left running. That real shop visit adds one scan
normally. Screenshots are `test-results/current-local-shop.png` and
`test-results/current-local-dashboard.png`.

Still mocked: payment (no real card charge) and lid acknowledgements when no
`LID_API_URL` is configured. Offline smoke tests deliberately simulate audio/model
providers; the separate live provider test actually called ElevenLabs and Luna.
No physical robot was actuated, and a microphone/speaker conversation was not
part of automated verification. No database or authentication system was added.
