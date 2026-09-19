import fs from "node:fs";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";

process.loadEnvFile("/home/admin/auto-dash/.env.local");

const client = new ElevenLabsClient({
    apiKey: process.env.ELEVENLABS_API_KEY
});

// Laura, with a friendly, conversational sales delivery.
const VOICE_ID = "FGY2WhTYpPnrIDTdsKH5";
const OUTPUT_DIR = "/home/admin/food_robot/audio/voice";
const voice = await client.voices.get(VOICE_ID);
if (!/laura/i.test(voice.name ?? "")) {
    throw new Error(`Expected Laura, received ${voice.name}. No clips were changed.`);
}
console.log(`Using voice: ${voice.name}`);

const phrases = {
    "question": "Hi there! Would you like something to eat?",
    "yes": "Great choice! Please scan the QR code to pay. Thank you!",
    "no": "No problem at all. Have a great day!",
    "paid": "Thanks so much! Enjoy your food, and come again!",

    "vendor1": "Food over here! Come take a look and grab something delicious.",
    "vendor2": "Feeling hungry? Take a little break and come grab a bite!",
    "vendor3": "Hello, everyone! Your next snack stop is right here. Come on over!",

    "funny1": "A little music and something tasty. Sounds like a good break to me!",
    "funny2": "Today's special? A snack break you didn't have to go looking for!",
    "funny3": "I run on batteries. You run on food. Let's get you sorted!",
    "funny4": "Beep beep! Your snack break has arrived. Come grab a bite!",
    "funny5": "Four wheels, one mission: helping hungry people find their next snack!",
    "funny6": "The future is here, and it brought food. Come see what's on offer!",
    "funny7": "Hungry folks, this way! Something delicious could make your day.",
    "funny8": "Busy day? You deserve a little food break. Stop by and say hello!",
    "funny9": "Why go looking for a snack when the snack shop comes to you?",
    "funny10": "Good food and a cheerful tune. Come take a look while I'm here!"
};


fs.mkdirSync(OUTPUT_DIR, {
    recursive: true
});

// Generate everything before replacing the active clips.
const generated = [];
for (const [name, text] of Object.entries(phrases)) {
    console.log(`Generating ${name}: "${text}"`);

    const audio = await client.textToSpeech.convert(VOICE_ID, {
        text,
        modelId: "eleven_multilingual_v2",
        outputFormat: "mp3_44100_128",
        voiceSettings: {
            stability: 0.5,
            similarityBoost: 0.8,
            style: 0.15,
            useSpeakerBoost: true,
            speed: 1.0
        }
    });

    const chunks = [];

    for await (const chunk of audio) {
        chunks.push(Buffer.from(chunk));
    }

    const data = Buffer.concat(chunks);
    if (!data.length) throw new Error(`Empty audio for ${name}. Active clips were not changed.`);
    generated.push({ name, data });
}

const backupDir = `${OUTPUT_DIR}/backup-${Date.now()}`;
fs.mkdirSync(backupDir);
for (const { name } of generated) {
    const target = `${OUTPUT_DIR}/${name}.mp3`;
    if (fs.existsSync(target)) fs.copyFileSync(target, `${backupDir}/${name}.mp3`);
}
for (const { name, data } of generated) {
    const target = `${OUTPUT_DIR}/${name}.mp3`;
    fs.writeFileSync(`${target}.tmp`, data);
    fs.renameSync(`${target}.tmp`, target);
}
console.log(`Previous clips saved in ${backupDir}`);
console.log("\nDONE! All robot voice clips generated.");
