"""Live context is re-fetched even within a conversation; model output cannot invent facts."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent, validate_reply
from vendi.conversation.context import VendigoContext


class LiveInventoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = {
            "robots": [{"id": "robot-001", "status": "available"}],
            "products": [{"id": "coke", "name": "Coca-Cola", "priceCents": 250},
                         {"id": "coke-zero", "name": "Coke Zero", "priceCents": 300},
                         {"id": "chips", "name": "Chips", "priceCents": 200}],
            "inventory": [{"robotId": "robot-001", "productId": "coke", "stock": 4},
                          {"robotId": "robot-001", "productId": "coke-zero", "stock": 7},
                          {"robotId": "robot-001", "productId": "chips", "stock": 2}],
            "activeOrders": [],
        }
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: self.data)
        self.http = SimpleNamespace(get=AsyncMock(return_value=response))
        http = self.http
        class Client:
            async def __aenter__(self): return http
            async def __aexit__(self, *args): pass
        self.patch = patch.dict("sys.modules", {"httpx": SimpleNamespace(AsyncClient=lambda **kwargs: Client())})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.gpt = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
        self.agent = ConversationAgent(VoiceConfig(), client=self.gpt)

    async def test_default_is_live_and_admin_purchase_changes_are_seen_without_restart(self):
        self.assertIsInstance(self.agent.context, VendigoContext)
        self.assertIn("4 left", (await self.agent.respond("How many Cokes do you have?")).text)
        self.data["inventory"][0]["stock"] = 3  # canonical purchase state
        self.assertIn("3 left", (await self.agent.respond("How many Cokes are left?")).text)
        self.data["inventory"][0]["stock"] = 9  # admin change
        self.assertIn("9 left", (await self.agent.respond("Do you have Coke?")).text)
        self.assertEqual(self.http.get.await_count, 3)
        self.gpt.responses.create.assert_not_called()

    async def test_zero_quantity_and_menu_cannot_claim_availability(self):
        self.data["inventory"][0]["stock"] = 0
        self.assertIn("sold out", (await self.agent.respond("Do you have Coke?")).text)
        menu = (await self.agent.respond("What do you have?")).text
        self.assertIn("Coca-Cola is sold out", menu)
        self.assertIn("Chips", menu)
        self.assertIn("7 left", (await self.agent.respond("Do you have Coke Zero?")).text)

    async def test_current_prices_and_fresh_structured_context_before_gpt(self):
        self.assertIn("2.50 CAD", (await self.agent.respond("How much is Coke?")).text)
        self.data["products"][0]["priceCents"] = 375
        self.data["inventory"][0]["stock"] = 1
        self.assertIn("3.75 CAD", (await self.agent.respond("How much is Coke?")).text)
        self.gpt.responses.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps({
            "reply": "We have a million!", "topic": "social", "intent": "CHECK_INVENTORY", "product_id": "coke"}))
        self.assertIn("1 left", (await self.agent.respond("Could you check the remaining Coca-Cola supply for me please?")).text)
        context = json.loads(self.gpt.responses.create.call_args.kwargs["input"][0]["content"])["VENDI_CONTEXT"]
        self.assertEqual(context["inventory"][0]["stock"], 1)
        self.assertEqual(context["prices"]["coke"], 375)
        # A repeated model intent must still report the same verified quantity,
        # rather than turning a correct fact into a duplicate-response fallback.
        self.assertIn("1 left", (await self.agent.respond("Please double-check that supply once more.")).text)

    async def test_unavailable_store_does_not_reuse_previous_facts_or_call_model(self):
        await self.agent.respond("Do you have Coke?")
        self.http.get.side_effect = OSError("offline")
        reply = await self.agent.respond("How many Cokes are left?")
        self.assertIn("trouble checking stock", reply.text)
        self.assertNotIn("4", reply.text)
        self.gpt.responses.create.assert_not_called()

    async def test_disabled_catalog_item_is_unavailable(self):
        self.data["products"][0]["enabled"] = False
        self.assertIn("sold out", (await self.agent.respond("Do you have Coke?")).text)

    async def test_model_quantity_prose_is_replaced_with_current_facts(self):
        context = await self.agent.context.snapshot()
        for prose in ("Coca-Cola has 999 left.", "There are 999 Cokes left.", "Three Cokes remaining."):
            reply = validate_reply({"reply": prose, "topic": "social", "intent": None, "product_id": "coke"}, context, "Please check the Coke supply.")
            self.assertIn("4 left", reply.text)

    async def test_plural_followups_keep_reference_but_refresh_quantity_and_price(self):
        self.assertIn("2 left", (await self.agent.respond("Do you have chips?")).text)
        self.data["products"][2]["priceCents"] = 125
        self.assertIn("1.25 CAD", (await self.agent.respond("How much are they?")).text)
        self.data["inventory"][2]["stock"] = 1
        self.assertIn("1 left", (await self.agent.respond("How many are left now?")).text)
        self.data["inventory"][2]["stock"] = 0
        self.assertIn("sold out", (await self.agent.respond("Do you have them?")).text)
        self.gpt.responses.create.assert_not_called()

    async def test_ampersands_and_spoken_and_resolve_to_the_same_live_product(self):
        for id, name, stock in [("kirkland-granola-bar", "Kirkland Soft & Chewy Granola Bar", 4),
                                ("brookside-acai-blueberry", "Brookside Acai & Blueberry Dark Chocolate", 1)]:
            self.data["products"].append({"id": id, "name": name, "priceCents": 100})
            self.data["inventory"].append({"robotId": "robot-001", "productId": id, "stock": stock})
            for label in (name, name.replace("&", "and")):
                self.assertIn(f"{stock} left", (await self.agent.respond(f"How many {label} are left?")).text)
                self.assertIn("1.00 CAD", (await self.agent.respond("How much are they?")).text)
        self.gpt.responses.create.assert_not_called()
