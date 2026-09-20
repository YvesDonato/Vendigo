"""Resolve explanation topics and validate procedural speech; never operate hardware."""

from enum import Enum
import re

from vendi.conversation.knowledge import LID_OPEN_SECONDS
from vendi.conversation.guardrails import guard_social_reply
from vendi.errors import VoiceFailure
from vendi.speech.yes_no import normalize


class PurchaseTopic(str, Enum):
    OVERVIEW = "purchase_overview"
    PICKUP = "purchase_pickup"
    FINISH = "purchase_finish"
    SECURITY = "purchase_security"
    TIMING = "purchase_timing"


TOPIC_STEP = {PurchaseTopic.OVERVIEW: "SCAN_AND_SELECT", PurchaseTopic.PICKUP: "VERIFIED_PAYMENT_AND_PICKUP",
              PurchaseTopic.FINISH: "AUTO_CLOSE_AND_RETURN", PurchaseTopic.TIMING: "VERIFIED_PAYMENT_AND_PICKUP"}
NEXT_TOPIC = {"SCAN_AND_SELECT": PurchaseTopic.PICKUP, "VERIFIED_PAYMENT_AND_PICKUP": PurchaseTopic.FINISH}
NEXT_QUESTIONS = {"and then", "then what", "then", "what next", "whats next", "what happens next",
                  "what happens after that", "what about after that", "and after that", "after that"}


def question_text(transcript):
    text = " ".join(normalize(transcript).split())
    return re.sub(r"^(?:(?:um|uh|okay|ok|so)\s+)+", "", text)


def purchase_question(transcript, state):
    """Hints go to GPT with history, rather than short-circuiting its answer."""
    text = question_text(transcript)
    if text == "why" and state.topic == "order" and re.search(r"\b(pay|paid|payment|refund)\b", normalize(state.last_user_transcript or "")):
        return PurchaseTopic.SECURITY
    if text in NEXT_QUESTIONS and state.explaining_purchase:
        return NEXT_TOPIC.get(state.purchase_step, PurchaseTopic.FINISH)
    if (("qr" in text or "success page" in text or "scanning" in text) and
            re.search(r"\b(open|opens|unlock|unlocks|dispense|payment|paid)\b", text)):
        return PurchaseTopic.SECURITY
    if re.search(r"\bhow long\b", text) and ("open" in text or state.explaining_purchase):
        return PurchaseTopic.TIMING
    if re.search(r"\b(?:after|once|when) i (?:pay|paid)\b", text):
        return PurchaseTopic.PICKUP
    if re.search(r"\bhow (?:can|do|would) i (?:buy|purchase)\b", text):
        return PurchaseTopic.OVERVIEW
    if text in {"how does this work", "how does it work", "how do purchases work"}:
        return PurchaseTopic.OVERVIEW
    if re.search(r"\bhow (?:can|do) i (?:actually |physically )?(?:get|collect|pick up) (?:the |my )?(?:item|snack|drink)\b", text):
        return PurchaseTopic.PICKUP
    if text in {"why", "how", "what happens"} and state.explaining_purchase:
        return PurchaseTopic.SECURITY if state.topic == "payment_security" else state.last_purchase_topic
    return None


def resolved_question(topic, transcript, state):
    """Resolve ambiguous 'it' and 'then' to customer-facing meaning for the model."""
    if not topic:
        return None
    text = question_text(transcript)
    if text == "why":
        return ("Why must the backend verify payment instead of trusting a scan or payment-success page? Explain the reason."
                if topic == PurchaseTopic.SECURITY else
                "Why is the purchase step you just explained necessary? Explain the reason rather than repeating the instructions.")
    return {
        PurchaseTopic.OVERVIEW: "How does the customer begin buying? Explain scanning, selecting an available item, and paying in the web app; stop at payment.",
        PurchaseTopic.PICKUP: "What happens after the customer pays, and how do they retrieve the item? Explain backend verification and the pickup window, not scanning again.",
        PurchaseTopic.FINISH: "What happens after collecting the item? Explain automatic closing, goodbye/completion, and returning to vendor operation.",
        PurchaseTopic.SECURITY: "Does scanning the QR code or seeing a success page authorize OPENING THE COMPARTMENT? Answer no: only server-verified payment/order authorization does. The question is about the compartment, not opening a browser.",
        PurchaseTopic.TIMING: "How many seconds does the compartment stay open for collection? Answer the configured pickup time directly.",
    }[topic]


def validate_procedure(text, topic, context):
    """Reject bad timing/current-status claims while allowing conditional explanations."""
    normalized = normalize(text.replace("-", " "))
    for clause in re.split(r"[,;.!?]", text):
        clause = normalize(clause)
        if re.match(r"(?:only )?(?:once|when|if|after|until|before)\b", clause):
            continue
        # "Pickup comes after payment is verified" is a condition, not a receipt.
        clause = re.sub(r"\b(?:once|when|if|after|until|before) (?:the |your )?payment (?:is|has been) verified\b", "", clause)
        if re.search(r"\byour payment (?:is|was|has been) (?:verified|received|confirmed|successful)|"
                     r"\b(?:payment succeeded|ive received your payment|i received your payment|you have paid)|"
                     r"\b(?:the )?backend (?:has )?verified your payment\b", clause) and not context.payment_verified:
            raise VoiceFailure("llm", "Explain payment verification conditionally; do not claim payment was received.")
        if re.search(r"\b(?:ive|i have|i just) (?:opened|unlocked)|\b(?:the|your) (?:lid|compartment) is (?:open|unlocked)\b", clause):
            raise VoiceFailure("llm", "Explain the procedure without claiming you operated hardware.")
        if guard_social_reply(clause, context, "procedure explanation") is not None:
            raise VoiceFailure("llm", "Explain the procedure conditionally; do not insert product prices, stock, or current-status claims.")
    if re.search(r"\b(?:scanning (?:the )?qr code|the success page) (?:(?:opens|unlocks) (?:the |your |my )?(?:lid|compartment)|authorizes (?:dispensing|pickup))\b", normalized):
        raise VoiceFailure("llm", "Scanning and a success page never authorize dispensing; only a verified server-side event does.")
    for amount, unit in re.findall(r"\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|sixty)\s+(seconds?|minutes?)\b", normalized):
        if amount not in {str(LID_OPEN_SECONDS), "seven"} or not unit.startswith("second"):
            raise VoiceFailure("llm", f"Use the authoritative {LID_OPEN_SECONDS}-second pickup window.")
    if topic in (PurchaseTopic.PICKUP, PurchaseTopic.TIMING) and not re.search(r"\b(?:7|seven)\s*seconds?\b", normalized):
        raise VoiceFailure("llm", f"Answer pickup/timing questions with approximately {LID_OPEN_SECONDS} seconds.")
    if topic == PurchaseTopic.PICKUP and not re.search(r"\b(verif\w*|confirmed by the backend)\b", normalized):
        raise VoiceFailure("llm", "Explain that payment verification is required before the compartment opens.")
    if topic == PurchaseTopic.SECURITY and (not re.search(r"\b(backend|server\w*)\b", normalized) or not re.search(r"\bverif\w*\b", normalized)):
        raise VoiceFailure("llm", "Explain server-side verification, not authorization by scanning or a success page.")
    # Defense in depth, not a semantic proof of arbitrary prose. No text executes actions.
    return text


def procedure_fallback(topic, transcript):
    """Trusted contextual recovery only after a model answer and its repair fail."""
    if question_text(transcript) == "why" and topic == PurchaseTopic.OVERVIEW:
        return "The web app lets you choose your item and complete payment in one place. The backend then verifies the order before dispensing."
    return {
        PurchaseTopic.OVERVIEW: "Scan my QR code, choose an available item in the Vendigo web app, and pay there.",
        PurchaseTopic.PICKUP: f"Once the backend verifies your payment, the compartment opens for about {LID_OPEN_SECONDS} seconds so you can collect your item.",
        PurchaseTopic.FINISH: "After you collect it, the lid closes automatically. I say goodbye, wrap up the transaction, and return to selling.",
        PurchaseTopic.SECURITY: "The backend verifies the real payment and order before authorizing pickup. Scanning a QR code or seeing a success page can't prove that payment was received.",
        PurchaseTopic.TIMING: f"About {LID_OPEN_SECONDS} seconds, then the compartment closes automatically.",
    }[topic]
