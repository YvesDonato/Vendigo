import subprocess
import json
import time
from vosk import Model, KaldiRecognizer

SPEAKER = "plughw:0,0"
MIC = "plughw:1,0"
RATE = 16000
MODEL_PATH = "/home/admin/robot/vosk-model-small-en-us-0.15"

model = Model(MODEL_PATH)


def speak(text):
    print(f"🤖 {text}")

    subprocess.run([
        "espeak-ng",
        "-s", "150",
        "-w", "/tmp/robot_speech.wav",
        text
    ], stdout=subprocess.DEVNULL)

    subprocess.run([
        "aplay",
        "-D", SPEAKER,
        "/tmp/robot_speech.wav"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Small delay so the mic doesn't hear the end of the speaker
    time.sleep(0.5)


def listen_yes_no():
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

    print("🎤 LISTENING...")

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

                print(f'👤 Heard: "{text}"')

                words = text.split()

                if any(w in words for w in ["yes", "yeah", "yep", "sure"]):
                    return "yes"

                if any(w in words for w in ["no", "nope", "nah"]):
                    return "no"

    finally:
        mic.terminate()
        mic.wait()


print("\n🤖 CUSTOMER INTERACTION TEST\n")

speak("Hi! Would you like some food?")

answer = listen_yes_no()

if answer == "yes":
    print("✅ CUSTOMER WANTS FOOD")
    speak("Great! Please scan the QR code to pay.")

    # Payment detection will go here later.
    print("💳 WAITING FOR PAYMENT")

elif answer == "no":
    print("❌ CUSTOMER DOES NOT WANT FOOD")
    speak("No problem! Have a great day.")

print("\n🏁 Interaction finished.")
