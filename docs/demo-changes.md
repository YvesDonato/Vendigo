# Demo implementation report

Implemented and verified on 2026-09-20. See [README](../README.md) for setup and usage.

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
- **Persistence:** `data/state.json`, configurable with `VENDIGO_DATA_FILE`.
  An atomic file replacement commits inventory, purchases, orders and analytics.
- **Manual inventory:** `/dashboard` → Inventory → type integer quantities →
  Save Inventory. An open shop updates through the existing event stream.
- **Decrement:** canonical `completePurchase` runs once after the existing
  seven-second pickup has successfully relocked. Stock cannot go below zero.
- **Duplicates:** durable order IDs plus matching original request fields and a
  purchase-record check. Reload/retry/restart cannot repeat the decrement.
- **QR scans:** one successful visit registration per tab session, with browser
  session storage and durable server deduplication. Purchases do not add scans.
- **Recent Purchases:** actual persistent completed records, newest first, with
  product, price, timestamp and order ID; five shown, expandable to twenty.
- **Routes:** `/shop` for customers; `/dashboard` for operators. Existing
  `/shop/robot-001` links still work. The shop has no admin navigation.
- **Live Vendi facts:** before every turn, `VendigoContext` fetches `/api/state`.
  Direct answers and structured GPT runtime context use that current snapshot.
  Unknown/unavailable inventory produces an explicit failure response, never a
  guessed or cached stock value. Legacy Node voice also fetches fresh state.

## Verification results

- `npm test`: **23 passed**, including durable writes, duplicate/concurrent orders,
  stock validation, revenue, scans, conversion, restart recovery and hardware
  preservation. All seven original camera firmware file hashes match.
- Python voice suite: **83 passed**, including the existing speech/wake/history/
  seven-second guide tests and new fresh inventory/price/sold-out tests.
- Playwright: **7 passed** against production, covering phone/desktop layouts,
  separate customer/admin sessions, successful pickup, reload recovery, server
  timer after disconnect, live inventory editing, QR, API validation and absent
  camera/robot/admin shop UI.
- Actual backend stop/start: **Coke 5 → restart 5 → purchase 4 → restart 4**;
  purchase record and seven QR visits survived; duplicate replay changed nothing.
  Vendi queried the restarted server and answered **4 left**.
- `npm run lint`, `npm run typecheck`, `npm run build`, `git diff --check`: passed.
- `python3 -m vendi.voice_demo --smoke`: all seven offline paths passed.
- Generated all **34** reusable ElevenLabs phrase clips for the female voice,
  including cached error fallbacks, greetings and wake responses.
- `VOICE_SERVER_PORT=3140 npm run voice`: preserved ElevenLabs Speech Engine
  started successfully with the configured female voice; stopped after verification.
- Opt-in real providers (`.venv-vendi/bin/python tests/verify_live_voice.py`):
  passed against its own isolated production shop with existing API keys. Vendi
  answered **4 left**, then **3 left** immediately after purchase. Actual
  **GPT-5.6 Luna** returned the current quantity and the seven-second explanation.
  An admin change to zero produced **sold out**. Catalog pricing remained free.
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
