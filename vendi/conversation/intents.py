from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional

from vendi.speech.yes_no import normalize


class Intent(str, Enum):
    SHOW_MENU = "SHOW_MENU"
    CHECK_INVENTORY = "CHECK_INVENTORY"
    CHECK_PRICE = "CHECK_PRICE"
    START_PURCHASE = "START_PURCHASE"
    END_CONVERSATION = "END_CONVERSATION"


@dataclass(frozen=True)
class AgentReply:
    text: str
    intent: Optional[Intent] = None
    product_id: Optional[str] = None


ENDINGS = {"bye", "goodbye", "bye bye", "see you", "see ya", "catch you later", "thanks",
           "thank you", "okay thanks", "ok thanks", "thanks bye", "thank you bye", "never mind",
           "nevermind", "im done", "i am done", "thats all", "thats all thanks", "end conversation",
           "end the conversation", "stop talking", "leave me alone"}


def is_ending(text):
    return " ".join(normalize(text).split()) in ENDINGS


def product_text(text):
    # Catalog labels can use '&' while spoken questions use 'and'. Normalize
    # both identically without changing speech consent or wake-word handling.
    return " ".join(normalize(text.replace("&", " and ")).split())


def deterministic_intent(text, context=None):
    """Only unambiguous shop requests bypass GPT; keywords alone are not intents."""
    normalized = product_text(text)
    if is_ending(text):
        return Intent.END_CONVERSATION
    if normalized in {"menu", "show menu", "show me the menu", "can i see the menu"}:
        return Intent.SHOW_MENU
    if normalized in {"i want to buy", "id like to buy", "lets buy", "start purchase", "i want a snack"}:
        return Intent.START_PURCHASE
    products = {"snack", "snacks", "drink", "drinks", "chips", "candy", "soda", "water", "this", "that", "it"}
    if context is not None:
        products.update(product_text(item.name) for item in context.inventory)
        products.update(product_text(item.id) for item in context.inventory)
    products.update(name + "s" for name in list(products) if not name.endswith("s"))
    product = r"(?:(?:the|a|your|these|those) )?(?:" + "|".join(re.escape(name) for name in sorted(products)) + r")"
    if re.fullmatch(r"(?:price|prices|how much|how much is (?:it|this|that)|"
                    r"how much (?:is|are) " + product + r"|how much (?:does|do) " + product + r" cost|"
                    r"whats the price of " + product + r"|(?:is|are) " + product + r" (?:free|expensive))", normalized):
        return Intent.CHECK_PRICE
    if re.fullmatch(r"(?:inventory|what do you have|what (?:snacks|drinks) (?:do you have|are available)|"
                    r"(?:is|are) " + product + r" (?:in stock|available|sold out)|"
                    r"do you have " + product + r"|how many " + product + r" (?:(?:are )?left|do you have))(?: now)?", normalized):
        return Intent.CHECK_INVENTORY
    return None


def is_order_request(text):
    """Recognize this customer's transaction, not 'order of planets' or 'paid leave'."""
    text = normalize(text)
    return bool(re.fullmatch(r"(?:order|order status|payment|payment status|refund|"
                            r"i (?:already |just )?(?:paid|ordered)(?: \d+(?: dollars| cents)?)?(?: say payment succeeded)?)", text) or
                re.search(r"\b(?:my (?:order|payment|refund)|"
                          r"(?:did|have) you (?:charged?|refunded?) me|(?:was|am) i charged|"
                          r"(?:did|has) (?:my |the )?payment (?:work|succeed|go through))\b", text))


def is_hardware_request(text):
    # Explanations of motors are ordinary conversation; commands to Vendi are not.
    return bool(re.fullmatch(r"(?:(?:please|can you|could you|will you) )?"
                             r"(?:(?:go|move) (?:forward|backward)|turn (?:left|right)|"
                             r"(?:open|close|unlock|lock) (?:the |your )?(?:lid|compartment)|"
                             r"(?:start|stop|activate|disable) (?:the |your )?(?:motor|motors|servo|servos))"
                             r"(?: please)?", normalize(text)))


def match_product(text, context):
    text = product_text(text)
    matches = [(item.id, max((len(label) for label in (product_text(item.name), product_text(item.id))
                             if re.search(r"\b" + re.escape(label) + r"s?\b", text)), default=0))
               for item in context.inventory]
    longest = max((size for _, size in matches), default=0)
    winners = [id for id, size in matches if size == longest and size > 0]
    return winners[0] if len(winners) == 1 else None


def specific_stock_request(transcript):
    """Identify an item request only after the caller has classified a stock intent."""
    text = product_text(transcript)
    request = re.fullmatch(
        r"(?:(?:do you (?:have|sell|carry|stock)|have you got|can i (?:get|buy|have)|"
        r"i want|id like|are you selling) (.+?)|"
        r"(?:is|are) (.+?) (?:in stock|available|sold out)|"
        r"how many (.+?) (?:do you have|are left))(?: please| now)?", text)
    if not request:
        return False
    item = next(part for part in request.groups() if part)
    item = re.sub(r"^(?:any|some|a|an|the) ", "", item)
    return item not in {"anything", "anything else", "something", "snacks", "snack", "drinks", "drink",
                        "food", "menu", "something to eat", "something to drink", "it", "that", "them"}


def unavailable_stock(context, product=None):
    text = (f"Sorry, we're out of {product.name} right now. It's sold out." if product else
            "Sorry, we don't have that in stock.")
    names = [item.name for item in context.inventory
             if item.stock > 0 and (product is None or item.id != product.id)][:2]
    if names:
        text += " But we do have " + " and ".join(names) + " in stock."
    return text


def render_intent(intent, context, product_id=None, *, transcript=""):
    """Commercial facts are rendered from the snapshot, never from model-written prose."""
    if intent == Intent.END_CONVERSATION:
        return AgentReply("You got it. I'll be around.", intent)
    if intent == Intent.SHOW_MENU:
        return AgentReply("Scan the QR code and take a look. Window shopping is welcome!", intent)
    if intent == Intent.START_PURCHASE:
        return AgentReply("Now we're talking! Scan the QR code and pick your snack.", intent, product_id)
    product = next((item for item in context.inventory if item.id == product_id), None)
    if intent == Intent.CHECK_PRICE:
        if product is None:
            return AgentReply("Which snack caught your eye? The QR menu has the latest prices too.", intent)
        price = context.prices.get(product.id)
        text = (f"{product.name} is free!" if price == 0 else
                f"{product.name} is {price / 100:.2f} {context.currency.upper()}." if price is not None else
                "I don't have a verified price for that. Check the QR menu for me.")
        return AgentReply(text, intent, product.id)
    if intent == Intent.CHECK_INVENTORY:
        if not context.inventory_known:
            text = "I don't have the current stock list. Scan the QR code for the latest menu."
        elif product is not None:
            text = f"{product.name} is in stock—{product.stock} left." if product.stock > 0 else unavailable_stock(context, product)
        elif specific_stock_request(transcript):
            text = unavailable_stock(context)
        else:
            names = [item.name for item in context.inventory if item.stock > 0]
            text = ("Right now I've got " + ", ".join(names[:5]) + ". Take a look at the QR menu!" if names else
                    "Looks like we're out of snacks right now. You caught a popular little shop!")
            sold_out = [item.name for item in context.inventory if item.stock == 0]
            if names and sold_out:
                text += " " + ", ".join(sold_out[:5]) + " is sold out."
        return AgentReply(text, intent, product.id if product else None)
    raise ValueError("Unsupported intent")


def order_reply(text, context):
    if re.search(r"\b(pay|paid|payment|charged|charge|refund)\b", normalize(text)):
        return AgentReply("The application has verified your payment." if context.payment_verified is True else
                          "I can't confirm a payment here. Check your order screen for the verified status.")
    status_lines = {
        "opening": "Your order is being prepared for pickup.",
        "unlocked": "Your order is ready for pickup.",
        "locking": "Your pickup is being wrapped up.",
        "completed": "Your order is marked complete. Enjoy!",
        "failed": "Your order needs a hand. Check the order screen for help.",
        "lock_failed": "Your pickup needs an operator's attention. Check the order screen for help.",
    }
    return AgentReply(status_lines.get(context.order_status,
                      "I don't have a verified status for your order. Check your order screen for me."))
