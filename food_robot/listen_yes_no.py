import subprocess
import json
from vosk import Model, KaldiRecognizer

MODEL_PATH = "/home/admin/robot/vosk-model-small-en-us-0.15"
MIC = "plughw:1,0"
RATE = 16000

print("Loading speech model...")
model = Model(MODEL_PATH)

# Restrict vocabulary to the responses we care about.
recognizer = KaldiRecognizer(
    model,
    RATE,
    '["yes", "yeah", "yep", "sure", "no", "nope", "nah", "[unk]"]'
)

mic = subprocess.Popen(
    [
        "arecord",
        "-D", MIC,
        "-f", "S16_LE",
        "-r", str(RATE),
        "-c", "1",
        "-t", "raw",
        "--buffer-size=1600",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
)

print("\n🎤 LISTENING")
print('Say "yes" or "no".')
print("CTRL+C to stop.\n")

try:
    while True:
        data = mic.stdout.read(3200)

        if not data:
            continue

        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get("text", "").lower().strip()

            if not text:
                continue

            print(f'Heard: "{text}"')

            words = text.split()

            if any(word in words for word in ["yes", "yeah", "yep", "sure"]):
                print("✅ YES DETECTED\n")

            elif any(word in words for word in ["no", "nope", "nah"]):
                print("❌ NO DETECTED\n")

            else:
                print("❓ UNKNOWN\n")

except KeyboardInterrupt:
    print("\n🛑 Stopped.")

finally:
    mic.terminate()
    mic.wait()
