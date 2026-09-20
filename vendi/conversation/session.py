"""Conversation memory never counts as evidence of payment, stock, or order progress."""

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from typing import Optional

from vendi.conversation.intents import Intent, match_product
from vendi.conversation.purchase_guide import PurchaseTopic, TOPIC_STEP, NEXT_QUESTIONS, purchase_question, question_text, resolved_question
from vendi.speech.yes_no import normalize


@dataclass
class ConversationContext:
    topic: Optional[str] = None
    last_intent: Optional[str] = None
    referenced_product: Optional[str] = None
    referenced_product_name: Optional[str] = None  # Customer's requested label, not verified inventory.
    explaining_purchase: bool = False
    purchase_step: Optional[str] = None
    last_purchase_topic: Optional[str] = None
    last_assistant_response: Optional[str] = None
    last_user_transcript: Optional[str] = None

    def resolve(self, transcript, application):
        text = question_text(transcript)
        explicit_product = match_product(transcript, application)
        product = explicit_product or self.referenced_product
        product_scope = explicit_product or self.topic in {"product", "purchase_process", "payment_security"}
        fact_intent = None
        if product_scope and (product or self.referenced_product_name):
            if text in {"how much", "how much is it", "how much is that", "how much does it cost", "whats the price"}:
                fact_intent = Intent.CHECK_PRICE
            elif text in {"do you have that", "do you have it", "do you have that one", "is it available", "is it in stock"}:
                fact_intent = Intent.CHECK_INVENTORY
            elif text in {"can i get one", "can i buy it", "i want that one"}:
                fact_intent = Intent.START_PURCHASE
        topic = purchase_question(transcript, self)
        short = text in NEXT_QUESTIONS or text in {"why", "how", "how long", "what happens", "what about that one", "do you have it", "how much", "can i get one"}
        return {"is_followup": short or fact_intent is not None, "expected_purchase_topic": topic,
                "resolved_product_id": product if product_scope else explicit_product, "fact_intent": fact_intent,
                "requested_product_name": self.referenced_product_name if product_scope else None,
                "resolved_question": resolved_question(topic, transcript, self)}

    def remember(self, transcript, reply, topic, product_id=None):
        self.last_user_transcript = transcript
        self.last_assistant_response = reply.text
        self.last_intent = reply.intent.value if reply.intent else ("PURCHASE_HELP" if topic in set(PurchaseTopic) else None)
        if product_id:
            self.referenced_product = product_id
        if topic in set(PurchaseTopic):
            requested = re.search(r"\b(?:buy|purchase)\s+(?:a |an |the )?([\w-]+(?:\s+[\w-]+){0,3}?)(?:\s+from you)?[?.!]*$", transcript, re.I)
            if requested and normalize(requested[1]) not in {"something", "anything", "item", "snack", "drink", "one", "it", "that", "this"}:
                self.referenced_product_name = requested[1]
                if not product_id:
                    self.referenced_product = None  # Don't borrow the previous product's ID.
        if topic in set(PurchaseTopic):
            self.topic = "payment_security" if topic == PurchaseTopic.SECURITY else "purchase_process"
            self.explaining_purchase = True
            self.last_purchase_topic = topic
            self.purchase_step = TOPIC_STEP.get(topic, self.purchase_step)
        elif reply.intent in (Intent.SHOW_MENU, Intent.START_PURCHASE):
            self.topic, self.explaining_purchase = "purchase_process", True
            self.purchase_step = "SCAN_AND_SELECT"
            self.last_purchase_topic = PurchaseTopic.OVERVIEW
        else:
            self.topic = "product" if product_id or reply.intent in (Intent.CHECK_PRICE, Intent.CHECK_INVENTORY) else topic
            self.explaining_purchase = False
            self.purchase_step = self.last_purchase_topic = None

    def is_duplicate(self, text, transcript):
        if not self.last_assistant_response or question_text(transcript) in {"repeat", "repeat that", "say that again", "what did you say"}:
            return False
        previous, candidate = normalize(self.last_assistant_response), normalize(text)
        # A refreshed price or quantity is new information, even if its template is identical.
        if re.findall(r"\d+", previous) != re.findall(r"\d+", candidate):
            return False
        return previous == candidate or SequenceMatcher(None, previous, candidate).ratio() >= 0.93

    def as_dict(self):
        return {**asdict(self), "customer_progress_verified_by_conversation": False}
