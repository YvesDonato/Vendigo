# Lid API

`GET /api/v1/lid` reads the last commanded lid position.
`POST /api/v1/lid` accepts exactly `{"state":"open"}` (0 degrees) or
`{"state":"closed"}` (180 degrees). Both require a bearer token.
The contract is in [`../public/lid-openapi.json`](../public/lid-openapi.json),
served at `/lid-openapi.json` for API clients.

The API uses `robot_code/lid-api.token`, a separate, private key for external
clients. The ESP32 motor-controller credential stays on the server in
`robot_code/control.token`. Both files are ignored by Git. The API reads them
on each request so key rotation does not require a rebuild. Environment
overrides are documented in `.env.example`.

The local service listens at `http://127.0.0.1:8781`. Run these from the repo:

```bash
LID_API_TOKEN="$(cat robot_code/lid-api.token)"
LID_API_URL=http://127.0.0.1:8781

# Read status (no movement).
curl --fail-with-body --max-time 10 \
  -H "Authorization: Bearer $LID_API_TOKEN" "$LID_API_URL/api/v1/lid"

# Open; change open to closed to close.
curl --fail-with-body --max-time 10 \
  -H "Authorization: Bearer $LID_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"state":"open"}' "$LID_API_URL/api/v1/lid"
```

Example response:

```json
{"commanded_state":"closed","commanded_angle":180,"enabled":true,"position_feedback":false}
```

There is no lid-position sensor: this response confirms the controller's
command, not mechanical closure. A timeout can mean the command was accepted
but its reply was lost; read status before retrying. An open/close command is
idempotent. API startup makes no movement requests.

## Service and permanent HTTPS hostname

Build with `npm run build`, then install `lid-api.service` as a user systemd
service. `systemctl --user start lid-api` starts it;
`systemctl --user stop lid-api` stops it. This requires the laptop to remain
powered, the ESP32 to remain reachable, and the user service manager to run.
The service sets `LID_API_ONLY=1`: every route except `/api/v1/lid` and
`/lid-openapi.json` returns 404, even if Cloudflare's path filter is omitted.
Normal website instances leave this variable unset.

The user created the remotely managed tunnel `vendigo`
(`d42ffb19-6649-4751-baef-a938c3c5f9ba`). Save only its connector token in
`robot_code/cloudflare-tunnel.token` with mode 600. This file is ignored by Git;
it is different from the lid API client key. Never put this token in a curl
request. `lid-cloudflare.service` reads it without putting it on the process
command line. The connector is pinned in `robot_code/.cloudflared-bin`.

In that tunnel's Cloudflare dashboard, add a published application route:

- Hostname: `vendi.yvesdonato.com` (selected in the Cloudflare dashboard).
- Path: `^/(api/v1/lid|lid-openapi\.json)$`
- Service type: HTTP; URL: `127.0.0.1:8781`.
- Keep unmatched traffic on the default 404 route; do not publish the whole app.

Then install and start `lid-cloudflare.service` as a user service:

```bash
systemctl --user enable --now lid-cloudflare.service
systemctl --user status lid-cloudflare.service
```

Replace `LID_API_URL` with that HTTPS origin in the curl commands once DNS and
the tunnel are active. A trycloudflare quick URL changes on restart and is not
the permanent deployment described here. See [Cloudflare's dashboard tunnel
instructions](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).

Tests: `npm test` includes authentication, rejected input, both positions,
credential separation, status, and controller failure handling, using a mock
controller so no hardware moves.
