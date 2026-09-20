// ACEBOTT QD106 / ESP32 Max 1.0. Pins and direction bytes: bundled vehicle.h.
#include <WiFi.h>
#include <WebServer.h>
#include <atomic>
#include "RangeGuard.h"
#include "secrets.h"

constexpr uint8_t PWM1 = 19, PWM2 = 23, CLOCK = 18, ENABLE = 16, DATA = 5, LATCH = 17;
constexpr uint16_t MAX_LEASE_MS = 200;
constexpr uint8_t MAX_SPEED = 255;  // Vendor's 8-bit range; calibrate host PWM with wheels lifted.
constexpr uint8_t TRIG = 13, ECHO = 14;  // QD106 kit ultrasonic wiring.
constexpr uint8_t LID_SERVO = 25, SERVO_BITS = 16;
// Match the kit's bundled ESP32Servo defaults; preserve calibration for this lid.
constexpr uint16_t SERVO_HZ = 50, SERVO_MIN_US = 544, SERVO_MAX_US = 2400;
// On this assembled robot, the vendor's Forward (163) drove all wheels backward.
// Use its Backward pattern (92) for forward; verify turn orientation separately.
enum Direction : uint8_t { Stop = 0, Straight = 92, Left = 83, Right = 172 };

struct Motion {
  uint32_t session = 0, sequence = 0, deadline = 0;
  Direction direction = Stop;
  uint8_t speed = 0;
};

WebServer server(80);
portMUX_TYPE motorLock = portMUX_INITIALIZER_UNLOCKED;
Motion motion;
Direction appliedDirection = Stop;
uint8_t appliedSpeed = 0;
uint32_t lastMotorStopMs = 0;
uint16_t distanceMm = 0, stopDistanceCm = 50;  // Zero means no valid echo, never clear space.
uint32_t distanceAtMs = 0;
std::atomic<bool> networkReady{false};
bool lidAttached = false;
int16_t lidAngle = -1;  // No movement on boot; attach only on an explicit command.
uint16_t lidPulseUs = 0;

bool forwardBlocked(uint32_t now) {  // Caller holds motorLock.
  return rangeBlocksForward(distanceMm, uint32_t(now - distanceAtMs), stopDistanceCm);
}

void distanceTask(void *) {
  TickType_t next = xTaskGetTickCount();
  for (;;) {
    digitalWrite(TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG, LOW);
    // Separate task/core: a missing echo cannot block HTTP or the motor watchdog.
    const uint32_t pulse = pulseIn(ECHO, HIGH, 25000);
    portENTER_CRITICAL(&motorLock);
    distanceMm = distanceFromEcho(pulse);
    distanceAtMs = millis();
    portEXIT_CRITICAL(&motorLock);
    vTaskDelayUntil(&next, pdMS_TO_TICKS(60));
  }
}

String distanceFields() {
  portENTER_CRITICAL(&motorLock);
  const uint32_t now = millis();
  const uint16_t mm = distanceMm, cutoff = stopDistanceCm;
  const uint32_t age = now - distanceAtMs;
  const bool blocked = forwardBlocked(now);
  portEXIT_CRITICAL(&motorLock);
  String body = ",\"distance_guard\":true,\"distance_cm\":";
  body += mm ? String(mm / 10.0f, 1) : String("null");
  body += ",\"distance_age_ms\":" + String(age);
  body += ",\"distance_blocked\":" + String(blocked ? "true" : "false");
  body += ",\"stop_distance_cm\":" + String(cutoff);
  return body;
}

const char *directionName(Direction direction) {
  switch (direction) {
    case Straight: return "straight";
    case Left: return "left";
    case Right: return "right";
    default: return "stop";
  }
}

void stopMotion() {
  portENTER_CRITICAL(&motorLock);
  motion = Motion{};
  portEXIT_CRITICAL(&motorLock);
}

void writeMotors(Direction direction, uint8_t speed) {
  // Disable both bridges while changing direction, including on startup/stop.
  digitalWrite(ENABLE, HIGH);
  analogWrite(PWM1, 0);
  analogWrite(PWM2, 0);
  digitalWrite(LATCH, LOW);
  shiftOut(DATA, CLOCK, MSBFIRST, direction);
  digitalWrite(LATCH, HIGH);
  if (direction != Stop && speed > 0) {
    analogWrite(PWM1, speed);
    analogWrite(PWM2, speed);
    digitalWrite(ENABLE, LOW);
  }
}

void motorTask(void *) {
  TickType_t next = xTaskGetTickCount();
  for (;;) {
    const uint32_t now = millis();
    portENTER_CRITICAL(&motorLock);
    if (!networkReady.load() || (motion.session && int32_t(now - motion.deadline) >= 0)) {
      motion = Motion{};  // Expiry disarms: delayed packets cannot restart motion.
    }
    Motion current = motion;
    if (current.direction == Straight && forwardBlocked(now)) {
      current.direction = Stop;
      current.speed = 0;
    }
    const bool changed = current.direction != appliedDirection || current.speed != appliedSpeed;
    portEXIT_CRITICAL(&motorLock);
    if (changed) {
      writeMotors(current.direction, current.speed);
      portENTER_CRITICAL(&motorLock);
      appliedDirection = current.direction;
      appliedSpeed = current.speed;
      if (current.direction == Stop || current.speed == 0) lastMotorStopMs = millis();
      portEXIT_CRITICAL(&motorLock);
    }
    // Independent of WebServer: even a stalled/partial HTTP request cannot extend a lease.
    vTaskDelayUntil(&next, pdMS_TO_TICKS(10));
  }
}

bool authorized() {
  if (server.header("Authorization") == String("Bearer ") + CONTROL_TOKEN) return true;
  server.send(401, "application/json", "{\"error\":\"unauthorized\"}");
  return false;
}

bool number(const char *name, uint32_t &result) {
  if (!server.hasArg(name)) return false;
  const String value = server.arg(name);
  if (value.isEmpty() || value.length() > 10) return false;
  uint64_t parsed = 0;
  for (size_t i = 0; i < value.length(); ++i) {
    if (value[i] < '0' || value[i] > '9') return false;
    parsed = parsed * 10 + value[i] - '0';
    if (parsed > UINT32_MAX) return false;
  }
  result = uint32_t(parsed);
  return true;
}

String lidFields() {
  String body = ",\"servo_pin\":" + String(LID_SERVO);
  body += ",\"servo_enabled\":" + String(lidAttached ? "true" : "false");
  body += ",\"servo_angle\":" + (lidAngle < 0 ? String("null") : String(lidAngle));
  body += ",\"servo_pulse_us\":" + String(lidPulseUs);
  body += ",\"servo_pwm_duty\":" + String(lidAttached ? ledcRead(LID_SERVO) : 0);
  body += ",\"servo_frequency_hz\":" + String(lidAttached ? ledcReadFreq(LID_SERVO) : 0);
  return body;
}

void setLid() {
  if (!authorized()) return;
  uint32_t angle;
  if (!number("angle", angle) || angle > 180) {
    server.send(400, "application/json", "{\"error\":\"servo angle must be an integer from 0 to 180\"}");
    return;
  }
  // Core 3.3.12 assigns a separate 50 Hz timer from the motor PWM timers.
  if (!lidAttached) lidAttached = ledcAttach(LID_SERVO, SERVO_HZ, SERVO_BITS);
  if (!lidAttached) {
    server.send(503, "application/json", "{\"error\":\"servo PWM unavailable\"}");
    return;
  }
  const uint16_t pulse = SERVO_MIN_US + angle * (SERVO_MAX_US - SERVO_MIN_US) / 180;
  const uint32_t duty = (uint64_t(pulse) * SERVO_HZ * (1UL << SERVO_BITS) + 500000) / 1000000;
  if (!ledcWrite(LID_SERVO, duty)) {
    server.send(503, "application/json", "{\"error\":\"servo PWM write failed\"}");
    return;
  }
  lidAngle = angle;
  lidPulseUs = pulse;
  server.send(200, "application/json", String("{\"ok\":true") + lidFields() + "}");
}

void status() {
  if (!authorized()) return;
  portENTER_CRITICAL(&motorLock);
  const Motion current = motion;
  const Direction direction = appliedDirection;
  const uint8_t speed = appliedSpeed;
  const uint32_t stoppedAt = lastMotorStopMs;
  portEXIT_CRITICAL(&motorLock);
  String body = "{\"firmware\":\"lordbot-jev-2\",\"armed\":";
  body += current.session ? "true" : "false";
  body += ",\"direction\":\"" + String(directionName(direction)) + "\",\"speed\":" + String(speed);
  body += ",\"sequence\":" + String(current.sequence) + ",\"max_speed\":" + String(MAX_SPEED);
  body += ",\"forward_bits\":" + String(uint8_t(Straight));
  body += ",\"max_lease_ms\":" + String(MAX_LEASE_MS) + ",\"uptime_ms\":" + String(millis());
  body += ",\"last_stop_ms\":" + String(stoppedAt);
  body += ",\"pwm1_duty\":" + String(ledcRead(PWM1)) + ",\"pwm2_duty\":" + String(ledcRead(PWM2));
  body += ",\"pwm1_frequency_hz\":" + String(ledcReadFreq(PWM1)) + ",\"pwm2_frequency_hz\":" + String(ledcReadFreq(PWM2));
  body += ",\"driver_enabled\":" + String(digitalRead(ENABLE) == LOW ? "true" : "false");
  body += distanceFields();
  body += lidFields();
  body += ",\"mac\":\"" + WiFi.macAddress() + "\"}";
  server.send(200, "application/json", body);
}

void setStopDistance() {
  if (!authorized()) return;
  uint32_t cm;
  if (!number("cm", cm) || cm < 10 || cm > 100) {
    server.send(400, "application/json", "{\"error\":\"distance must be 10-100 cm\"}");
    return;
  }
  portENTER_CRITICAL(&motorLock);
  motion = Motion{};
  stopDistanceCm = cm;
  portEXIT_CRITICAL(&motorLock);
  server.send(200, "application/json", String("{\"ok\":true") + distanceFields() + "}");
}

void arm() {
  if (!authorized()) return;
  if (!networkReady.load()) {
    server.send(503, "application/json", "{\"error\":\"Wi-Fi disconnected\"}");
    return;
  }
  const uint32_t session = esp_random() | 1;
  portENTER_CRITICAL(&motorLock);
  motion = Motion{};
  motion.session = session;
  motion.deadline = millis() + 500;
  portEXIT_CRITICAL(&motorLock);
  server.send(200, "application/json", "{\"session\":" + String(session) + "}");
}

void drive() {
  if (!authorized()) return;
  uint32_t session, sequence, speed, lease;
  Direction direction = Stop;
  const String requested = server.arg("direction");
  if (requested == "straight") direction = Straight;
  else if (requested == "left") direction = Left;
  else if (requested == "right") direction = Right;
  else if (requested != "stop") {
    stopMotion();
    server.send(400, "application/json", "{\"error\":\"invalid direction\"}");
    return;
  }
  if (!number("session", session) || !number("sequence", sequence) || !number("speed", speed)
      || !number("lease_ms", lease) || speed > MAX_SPEED || lease < 20 || lease > MAX_LEASE_MS) {
    stopMotion();
    server.send(400, "application/json", "{\"error\":\"invalid control limits\"}");
    return;
  }
  const uint32_t now = millis();
  portENTER_CRITICAL(&motorLock);
  const bool accepted = networkReady.load() && session && session == motion.session
      && sequence > motion.sequence && int32_t(now - motion.deadline) < 0;
  if (accepted) {
    motion.sequence = sequence;
    motion.direction = direction;
    motion.speed = direction == Stop ? 0 : speed;
    motion.deadline = now + lease;
  }
  portEXIT_CRITICAL(&motorLock);
  if (accepted) server.send(200, "application/json", "{\"ok\":true,\"expires_ms\":" + String(now + lease) + distanceFields() + "}");
  else server.send(409, "application/json", "{\"error\":\"disarmed or stale sequence\"}");
}

void setup() {
  digitalWrite(ENABLE, HIGH);
  pinMode(ENABLE, OUTPUT);
  for (const uint8_t pin : {PWM1, PWM2, CLOCK, DATA, LATCH}) pinMode(pin, OUTPUT);
  analogWriteResolution(PWM1, 8);
  analogWriteResolution(PWM2, 8);
  writeMotors(Stop, 0);
  digitalWrite(TRIG, LOW);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  Serial.begin(115200);
  Serial.println("LordBotJev v2: disarmed; front ultrasonic guard at 50 cm");
  if (xTaskCreatePinnedToCore(motorTask, "motor-watchdog", 4096, nullptr, 3, nullptr, 1) != pdPASS) {
    Serial.println("Watchdog failed; halted with motors disabled");
    for (;;) delay(1000);
  }
  if (xTaskCreatePinnedToCore(distanceTask, "front-distance", 2048, nullptr, 1, nullptr, 0) != pdPASS) {
    Serial.println("Distance task failed; halted with motors disabled");
    for (;;) delay(1000);
  }
  WiFi.onEvent([](WiFiEvent_t event) {
    if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) networkReady.store(true);
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) networkReady.store(false);
  });
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("lordbot-jev");
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  const char *headers[] = {"Authorization"};
  server.collectHeaders(headers, 1);
  server.on("/status", HTTP_GET, status);
  server.on("/stop-distance", HTTP_POST, setStopDistance);
  server.on("/arm", HTTP_POST, arm);
  server.on("/drive", HTTP_POST, drive);
  server.on("/servo", HTTP_POST, setLid);
  server.on("/stop", HTTP_POST, []() {
    if (!authorized()) return;
    stopMotion();
    server.send(200, "application/json", "{\"ok\":true}");
  });
  server.onNotFound([]() { server.send(404, "application/json", "{\"error\":\"not found\"}"); });
  server.begin();
}

void loop() {
  static bool reported = false;
  if (networkReady.load() && !reported) {
    Serial.print("LordBot ready: http://");
    Serial.println(WiFi.localIP());
    reported = true;
  }
  if (!networkReady.load()) reported = false;
  server.handleClient();
  delay(1);
}
