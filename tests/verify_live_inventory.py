"""Exercise one long-lived Vendi conversation against an isolated running web app.

Used by Playwright's restart test. Mutates only the explicitly supplied test data
directory; speech/model providers are not needed for factual inventory questions.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent
from vendi.conversation.context import VendigoContext


async def check(base, directory):
    import httpx
    path = Path(directory) / 'inventory.json'
    agent = ConversationAgent(VoiceConfig(), VendigoContext(base))
    replies = []

    async def ask(question, expected):
        reply = (await agent.respond(question)).text
        assert expected in reply, (question, reply, expected)
        replies.append(reply)

    try:
        async with httpx.AsyncClient(base_url=base, timeout=10) as client:
            async def stock(quantity):
                response = await client.post('/api/inventory', json={
                    'robotId': 'robot-001', 'items': [{'productId': 'rice-krispies-original', 'stock': quantity}]})
                response.raise_for_status()

            await stock(3)
            await ask('How many Rice Krispies Treats Original are left?', '3 left')
            await ask('How much is it?', '1.00 CAD')
            before = (await client.get('/api/state')).json()
            order = {'orderId': 'live-inventory-test', 'robotId': 'robot-001',
                     'productId': 'rice-krispies-original', 'compartmentId': 1, 'sessionId': 'live-inventory-test'}
            (await client.post('/api/purchases', json=order)).raise_for_status()
            for _ in range(120):
                state = (await client.get('/api/state')).json()
                if len(state['transactions']) == len(before['transactions']) + 1:
                    break
                await asyncio.sleep(.1)
            assert state['inventory'][0]['stock'] == 2, state['inventory']
            assert len(state['transactions']) == len(before['transactions']) + 1
            assert sum(p['amountCents'] for p in state['transactions']) == sum(p['amountCents'] for p in before['transactions']) + 100
            (await client.post('/api/purchases', json=order)).raise_for_status()
            await ask('How many Rice Krispies Treats Original are left?', '2 left')
            await stock(9)
            await ask('How many are left now?', '9 left')

            catalog = json.loads(path.read_text())
            product = next(p for p in catalog['products'] if p['id'] == 'rice-krispies-original')
            product.update(inventory=6, price=2.25)
            path.write_text(json.dumps(catalog))
            await ask('How many Rice Krispies Treats Original are left?', '6 left')
            await ask('How much are they?', '2.25 CAD')
            product['inventory'] = 0
            path.write_text(json.dumps(catalog))
            await ask('Do you have them?', 'sold out')
            denied = await client.post('/api/purchases', json={**order, 'orderId': 'out-of-stock'})
            assert denied.status_code == 409

            path.write_text('{broken')
            await ask('How many Rice Krispies Treats Original are left?', "trouble checking stock")
            assert path.read_text() == '{broken'
            product['inventory'] = 9
            path.write_text(json.dumps(catalog))
            await ask('How many Rice Krispies Treats Original are left?', '9 left')
            await ask('How much is it?', '2.25 CAD')
        print(json.dumps({'same_session_replies': replies}), flush=True)
    finally:
        await agent.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args()
    asyncio.run(check(args.base_url, args.data_dir))
