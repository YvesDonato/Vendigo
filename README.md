# Vendigo

**Commerce that comes to you.**

Vendigo is an autonomous mobile storefront for crowded events. A small robot brings cold drinks and snacks to the crowd. Customers scan its QR code, pick one free item, confirm, and collect it from an unlocked compartment. Operators see inventory, pickup activity, robot controls, and an onboard camera in one live dashboard. The mobile-first interface uses white and sky blue without shadows, decorative badges, location labels, or fleet numbers.

## Run locally

Requires Node.js **22.18+** and npm.

```bash
npm ci
npm run dev
```

No accounts, API keys, payment provider, or database are required. Optional configuration is documented in [.env.example](.env.example); put your values in `.env.local`.

- Customer storefront: **http://localhost:3000/shop/robot-001**
- Operator dashboard: **http://localhost:3000/dashboard**
- `/` opens the default robot’s storefront.

For a production demo:

```bash
npm run build
npm start
```

### Scanning from a phone

Run the app on a computer connected to the same reachable Wi-Fi network as the phone. Open the dashboard using the computer’s LAN address, such as `http://192.168.1.42:3000/dashboard`, and select **Robot QR**. Download the PNG and attach it to the robot. The QR points to the same origin at `/shop/robot-001`.

Alternatively, set `NEXT_PUBLIC_SHOP_ORIGIN=http://192.168.1.42:3000` before starting development or **before building** production. A QR containing `localhost` only works on the computer itself. The QR dialog calls this out. All fonts, icons, and product illustrations are bundled locally.

## The demo

1. Keep `/dashboard` open on a laptop.
2. Scan the QR with a phone, or open `/shop/robot-001` in another browser.
3. Choose **Coca-Cola → Get Item → Confirm**.
4. All items are **Free**. Confirmation goes straight to unlocking, with no payment step.
5. The server acknowledges the unlock; the customer sees **Compartment unlocked**, **Take your Coca-Cola**, and a seven-second countdown.
6. After seven seconds, the **server** relocks the compartment, deducts one unit, and records the sale.
7. Units sold, conversion, inventory, and recent sales update in all open dashboards without refreshing. Free pickups record zero-value transactions, so revenue stays at $0.00.

Closing or refreshing the customer’s tab does not cancel the relock timer. Refreshing during a pickup restores the active order. A repeated request reuses the order ID and cannot record a second sale. Only one compartment per robot can be active at a time.

The demo starts with **$0.00 CAD revenue, 97 free pickups, 143 scans, 67.8% conversion, and 34 items on board**. These numbers are derived from seed transaction rows and inventory records. Conversion measures unique pickup sessions divided by scanned sessions; repeat pickups in one session increase units without counting another converted session. One scan is counted per robot per browser-tab session.

**Stop**, **Resume**, **Return to Base**, and operator **Unlock Compartment** use the shared backend. A manual unlock automatically relocks without creating a purchase or reducing stock. Movement commands are blocked while a compartment is open. A stop takes priority over an in-flight resume. Failed locks stop the robot, keep the compartment reserved, and expose **Retry lock** to the operator.

## Architecture

Next.js 16 App Router, React, TypeScript, plain CSS, and one in-memory Node.js store. No separate backend service is needed.

```text
src/
  app/
    shop/[robotId]/          Customer route, resolves the QR's robot ID
    dashboard/              Operator route
    api/
      state/                Snapshot + polling fallback
      events/               Server-sent event stream
      scans/                Idempotent scan registration
      orders/[orderId]/      Order recovery and pickup status
      robot/unlock/         Customer purchase/unlock
      robot/command/        Operator controls
      camera/               MJPEG proxy and configuration status
  components/
    storefront/             Catalog and purchase dialog
    dashboard/              Metrics, inventory, sales, QR
    robot/                  Robot status and controls
    camera/                 Isolated live camera viewer
  hooks/use-live-state.ts   Live snapshots with polling fallback
  lib/
    demo-data.ts            One consistent event seed
    server/store.ts         Inventory, orders, timers, transactions
    server/runtime.ts       Process-wide store shared by route handlers
    robot/hardware.ts       Replaceable physical vehicle adapter
    camera/config.ts        Server-only camera URL configuration
  types/                    Robot, Product, InventoryItem, Transaction,
                            VenueLocation, RobotCommand, and shared state
public/
  products/                 Replaceable local SVG product illustrations
  robot.svg                 Vendigo illustration
camera_code/                Original ESP32 firmware, preserved unchanged
tests/                      Backend and browser verification
```

The store publishes a complete snapshot after mutations. Both interfaces subscribe to `/api/events`; a three-second polling fallback keeps data moving when a proxy does not support event streams. Hardware acknowledgements control the order state. Money is stored as integer cents; all catalog prices are zero. Revenue charts and the sales feed are derived from the same transaction collection.

**Run one long-lived Node.js process for this prototype.** State resets to seed data when the server restarts. It is intentionally not durable and should not be deployed across multiple serverless workers or instances. Timers survive browser disconnects, not process shutdowns. Before controlling real hardware, the robot must enforce its own physical auto-lock watchdog. The current app has no authentication and is intended for a trusted demo environment.

Robot movement and battery telemetry are simulated; camera status reflects the connected feed. Robot IDs and location data remain internal to inventory, orders, hardware calls, and transactions, but locations and fleet numbers are not displayed in the UI. To add another demo robot, add its robot and inventory records to the seed; `/shop/[robotId]` already supports it. The dashboard focuses on the first robot while event metrics aggregate all transactions.

## Robot hardware integration

Set `LID_API_URL=https://vendi.yvesdonato.com/api/v1/lid` on the website server
to enable the physical lid. Set `LID_API_KEY` to the dedicated lid API key on a
hosted website; this laptop can read the existing `robot_code/lid-api.token`
instead. These are server-only settings. Leave `LID_API_URL` empty for simulation.

A confirmed purchase sends `{"state":"open"}`. After acknowledgement, the
existing seven-second server timer sends `{"state":"closed"}` even if the browser
is closed or refreshed. All catalog compartments share this robot's one lid.
Failed close requests use the existing operator **Retry lock** flow and do not
complete the sale. Position acknowledgements are commands, not physical sensor
feedback. The website server, tunnel, and lid API must remain running; the timer
does not survive a website-server restart.

The shared adapter in [src/lib/robot/hardware.ts](src/lib/robot/hardware.ts)
handles these operations (wheel commands remain simulated):

```ts
unlockCompartment(robotId, compartmentId)
lockCompartment(robotId, compartmentId)
stopRobot(robotId)
resumeRobot(robotId)
returnToBase(robotId)
```

Resolve a call only after the vehicle acknowledges it, and reject on errors or timeouts. Keep inventory, arbitration, and the order lifecycle in the store. All products are free; there is no payment step, Stripe integration, or charge.

The customer endpoint accepts:

```http
POST /api/robot/unlock
Content-Type: application/json

{
  "robotId": "robot-001",
  "productId": "coke",
  "compartmentId": 1,
  "orderId": "a-unique-order-id",
  "sessionId": "a-browser-session-id"
}
```

`orderId` is the idempotency key; retries must preserve it and the other fields. Product-to-compartment mappings, availability, and stock are validated by the server. The response contains the order status and the absolute `closesAt` deadline. Relocking is server-owned and does not require a browser request.

Operator commands use `POST /api/robot/command` with `robotId` and `command`: `stop`, `resume`, `return-to-base`, `unlock`, or `retry-lock`. `unlock` additionally requires `compartmentId`.

## Camera integration

The original camera implementation is preserved **byte for byte** in `camera_code/CameraWebServer_htn/`:

| File | Preserved functionality |
| --- | --- |
| `CameraWebServer_htn.ino` | ESP32 camera initialization, Wi-Fi, sensor and PSRAM setup; active AI Thinker pin selection |
| `app_httpd.cpp` | Camera HTTP endpoints, JPEG capture, controls, MJPEG streaming, and LED handling |
| `camera_pins.h` | All existing board pin mappings |
| `board_config.h` | Original alternative board configuration |
| `camera_index.h` | Embedded camera control web UI |
| `partitions.csv` | Firmware partition configuration |
| `ci.yml` | Existing ESP32 build matrix |

No camera hooks, React components, web API routes, or npm dependencies existed in the original application. The camera runs independently using the ESP32 Arduino camera/Wi-Fi libraries; the rebuild does not change its firmware dependencies or configuration.

The firmware exposes its native control UI on port **80** and its MJPEG stream at **`http://CAMERA_IP:81/stream`**. Read the device’s IP from its existing serial output, and configure:

```dotenv
CAMERA_STREAM_URL=http://192.168.1.123:81/stream
```

Restart the app after setting the variable. **Live Robot Camera** uses a native MJPEG image element and proxies the stream through `/api/camera/stream`. The proxy preserves the multipart content type and frame bytes. Only the server-configured destination is accepted. A same-origin proxy avoids browser CORS and mixed-content problems; the **Next.js server** must still be able to reach the camera’s network.

Without a configured camera, or when the stream fails, the dashboard shows a proper offline panel and **Reconnect camera**. It never substitutes a fake live feed. Camera status in the robot card follows the viewer. The camera code is checked against pre-rebuild SHA-256 hashes in the backend tests. Browser tests use an actual multipart JPEG fixture to verify the proxy, online state, offline behavior, and reconnect; physical hardware still needs an on-venue check.

## Verification

```bash
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests start production instances on ports **3100/3101**, plus an isolated MJPEG fixture on **3102**, and shut them down afterward. They verify phone/desktop layouts, a purchase across separate browser sessions, page-reload recovery, tab-disconnect relocking, all related metrics, robot controls, manual unlocks, QR generation, invalid API requests, unknown robots, and camera reconnects. Screenshots are written to the ignored `test-results/` directory.

## Project name

The website, metadata, package, and documentation use **Vendigo** (`vendigo` for the npm package name). The [GitHub repository](https://github.com/ericpungholee/Vendigo) is named **Vendigo**, and this checkout’s `origin` points to `git@github.com:ericpungholee/Vendigo.git`.

The local checkout directory and installed robot-service paths keep their existing filesystem names so the running app and hardware services continue working. Legacy internal session keys are retained for pickup recovery.

## Robot voice and customer interaction

The earlier voice server (`npm run voice`), voice and agent API routes, and
agent modules are preserved alongside the storefront/dashboard. Their original
React components remain available but are not mounted in the new dashboard.
See [vendor audio](food_robot/README.md) and
[customer interaction controller](food_robot/CUSTOMER_FLOW.md) for robot setup
and simulation tests. The customer controller still needs live hardware adapters.

Active audio assets are included under `food_robot/audio`; for a different
checkout location, pass `--audio-dir ./food_robot/audio` to the vendor player.
