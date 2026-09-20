"""Opt-in real ElevenLabs STT/TTS + GPT check against an isolated production web app.
Run after npm run build: .venv-vendi/bin/python tests/verify_live_voice.py
Uses existing API keys/credits, never an operator's inventory or physical hardware.
"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent
from vendi.conversation.context import VendigoContext
from vendi.speech.scribe import ScribeSTT
from vendi.speech.tts import ElevenLabsTTS


async def check(base):
    import httpx
    config = VoiceConfig.from_env()
    agent = ConversationAgent(config, VendigoContext(base))
    tts = ElevenLabsTTS(config)
    try:
        async with httpx.AsyncClient(base_url=base, timeout=10) as client:
            for _ in range(100):
                try:
                    if (await client.get('/api/state')).is_success:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError('Test website did not start')
            async def inventory(quantity):
                response = await client.post('/api/inventory', json={
                    'robotId': 'robot-001', 'items': [{'productId': 'coke', 'stock': quantity}]})
                response.raise_for_status()
            await inventory(4)
            reply = await agent.respond('How many Cokes are left?')
            assert '4 left' in reply.text, reply.text
            print('Admin → Vendi:', reply.text, flush=True)
            response = await client.post('/api/purchases', json={
                'orderId': 'voice-live-purchase', 'robotId': 'robot-001', 'productId': 'coke',
                'compartmentId': 1, 'sessionId': 'live-voice-test'})
            response.raise_for_status()
            for _ in range(100):
                state = (await client.get('/api/state')).json()
                if state['transactions']:
                    break
                await asyncio.sleep(0.1)
            assert state['inventory'][0]['stock'] == 3
            reply = await agent.respond('How many Cokes are left?')
            assert '3 left' in reply.text, reply.text
            print('Purchase → Vendi:', reply.text, flush=True)
            # Deliberately use a non-shortcut request so the real GPT integration runs.
            reply = await agent.respond('Please look up the exact remaining Coca-Cola supply for me today.')
            assert '3 left' in reply.text, reply.text
            print('GPT + fresh context:', reply.text, flush=True)
            reply = await agent.respond('How long do I have to collect my item after verification?')
            assert 'seven' in reply.text.lower() or '7' in reply.text, reply.text
            print('GPT dispensing knowledge:', reply.text, flush=True)
            await inventory(0)
            reply = await agent.respond('Do you have Coke?')
            assert 'sold out' in reply.text, reply.text
            print('Sold out → Vendi:', reply.text, flush=True)
            reply = await agent.respond('How much is Coke?')
            assert '1.00 CAD' in reply.text, reply.text
            print('Catalog price:', reply.text, flush=True)
        sample = ROOT / 'test-results/vendi-matilda.wav'
        await tts.generate_clip("Hey there! I'm Vendi. Ready for a little snack break? Scan my QR code and see what catches your eye.", sample)
        print('ElevenLabs TTS:', sample.relative_to(ROOT), flush=True)
        transcript = await ScribeSTT(config).transcribe_file(str(sample))
        assert 'snack' in transcript.lower() or 'qr' in transcript.lower(), transcript
        print('ElevenLabs STT:', transcript, flush=True)
    finally:
        await agent.close()
        await tts.close()


def main():
    with tempfile.TemporaryDirectory(prefix='vendigo-live-') as directory:
        env = {**os.environ, 'VENDIGO_DATA_FILE': str(Path(directory) / 'state.json'),
               'LID_API_URL': '', 'LID_API_ONLY': ''}
        with tempfile.TemporaryFile() as log:
            server = subprocess.Popen(['node', 'node_modules/next/dist/bin/next', 'start',
                                       '--hostname', '127.0.0.1', '--port', '3135'],
                                      cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                asyncio.run(check('http://127.0.0.1:3135'))
            finally:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == '__main__':
    main()
