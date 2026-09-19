/** The ESP32 sketch is preserved in camera_code/CameraWebServer_htn/.
 * Its HTTP server uses port 80 and its native MJPEG stream uses port 81.
 * Only a server-configured URL is accepted; clients cannot proxy arbitrary URLs.
 */
export function cameraStreamUrl() {
  const configured = process.env.CAMERA_STREAM_URL;
  if (!configured) return null;
  try {
    const url = new URL(configured);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch { return null; }
}
