import { createServer } from "node:http";

let frame = null;
let available = true;
const streams = new Set();

const server = createServer(async (request, response) => {
  if (request.url === "/health") { response.end("ok"); return; }
  if (request.url === "/frame" && request.method === "POST") {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    frame = Buffer.concat(chunks);
    available = true;
    response.end("ok");
    return;
  }
  if (request.url === "/offline" && request.method === "POST") {
    available = false;
    for (const stream of streams) stream.end();
    response.end("ok");
    return;
  }
  if (request.url !== "/stream" || !available || !frame) {
    response.writeHead(503); response.end("Camera offline"); return;
  }
  response.writeHead(200, { "Content-Type": "multipart/x-mixed-replace;boundary=hawk-camera-test", "Cache-Control": "no-store" });
  streams.add(response);
  const send = () => {
    response.write(`\r\n--hawk-camera-test\r\nContent-Type: image/jpeg\r\nContent-Length: ${frame.length}\r\n\r\n`);
    response.write(frame);
  };
  send();
  const timer = setInterval(send, 200);
  response.on("close", () => { clearInterval(timer); streams.delete(response); });
});

server.listen(3102, "127.0.0.1");
process.on("SIGTERM", () => { for (const stream of streams) stream.end(); server.close(); });
