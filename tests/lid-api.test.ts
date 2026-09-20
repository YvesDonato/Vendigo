import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GET, POST } from "../src/app/api/v1/lid/route.ts";
import { proxy } from "../src/proxy.ts";

test("lid API authenticates, restricts commands, and reports controller failures", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "lid-api-test-"));
  const keys = ["LID_API_TOKEN_FILE", "LID_CONTROLLER_TOKEN_FILE", "LID_CONTROLLER_URL", "LID_API_ONLY"];
  const before = keys.map((key) => process.env[key]);
  t.after(async () => {
    keys.forEach((key, i) => { if (before[i] === undefined) delete process.env[key]; else process.env[key] = before[i]; });
    await rm(directory, { recursive: true, force: true });
  });
  const apiToken = "test-api-token-".repeat(4);
  process.env.LID_API_ONLY = "1";
  for (const path of ["/", "/api/robot/command", "/api/agent", "/arm", "/servo"]) {
    assert.equal(proxy(new Request("http://localhost" + path))?.status, 404);
  }
  assert.equal(proxy(new Request("http://localhost/api/v1/lid")), undefined);
  assert.equal(proxy(new Request("http://localhost/lid-openapi.json")), undefined);
  delete process.env.LID_API_ONLY;
  assert.equal(proxy(new Request("http://localhost/dashboard")), undefined);
  process.env.LID_API_TOKEN_FILE = join(directory, "api.token");
  process.env.LID_CONTROLLER_TOKEN_FILE = join(directory, "controller.token");
  process.env.LID_CONTROLLER_URL = "http://controller.invalid";
  await writeFile(process.env.LID_API_TOKEN_FILE, apiToken, { mode: 0o600 });
  await writeFile(process.env.LID_CONTROLLER_TOKEN_FILE, "private-controller-token", { mode: 0o600 });
  const calls: { url: string; method: string; body: string | undefined }[] = [];
  let failure = 0;
  t.mock.method(globalThis, "fetch", async (url: URL, init: RequestInit) => {
    assert.equal(new Headers(init.headers).get("Authorization"), "Bearer private-controller-token");
    calls.push({ url: String(url), method: init.method!, body: init.body?.toString() });
    if (failure === 504) throw new DOMException("upstream private detail", "TimeoutError");
    if (failure) return new Response("upstream private detail", { status: failure });
    return Response.json({ ok: true, servo_enabled: true, servo_angle: init.body ? Number(new URLSearchParams(init.body.toString()).get("angle")) : 180, mac: "private" });
  });
  const request = (body?: object, token = apiToken) => new Request("http://localhost/api/v1/lid", {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  assert.equal((await GET(request(undefined, "wrong"))).status, 401);
  assert.equal((await POST(request({ state: "open" }, "wrong"))).status, 401);
  assert.equal((await POST(request({ state: "toggle" }))).status, 400);
  assert.equal((await POST(request({ state: "open", direction: "straight" }))).status, 400);
  assert.equal(calls.length, 0);
  for (const [state, angle] of [["open", 0], ["closed", 180]] as const) {
    const result = await POST(request({ state }));
    assert.equal(result.status, 200);
    assert.equal(result.headers.get("Cache-Control"), "no-store");
    assert.deepEqual(await result.json(), { commanded_state: state, commanded_angle: angle, enabled: true, position_feedback: false });
    assert.deepEqual(calls.at(-1), { url: "http://controller.invalid/servo", method: "POST", body: `angle=${angle}` });
  }
  assert.equal((await GET(request())).status, 200);
  assert.equal(calls.at(-1)?.url, "http://controller.invalid/status");
  failure = 500;
  const failed = await POST(request({ state: "closed" }));
  assert.equal(failed.status, 502);
  assert.ok(!(await failed.text()).includes("private"));
  failure = 504;
  assert.equal((await GET(request())).status, 504);
  await rm(process.env.LID_API_TOKEN_FILE);
  assert.equal((await GET(request())).status, 503);
});
