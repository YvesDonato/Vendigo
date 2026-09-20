"""Scope commercial checks to vendor claims, allowing numbers and general knowledge.

These checks back up the constrained prompt/schema; they are not a semantic proof
of arbitrary text. Actual commercial facts always come from application templates.
"""

import re

from vendi.conversation.intents import AgentReply, Intent, deterministic_intent, match_product, order_reply, render_intent
from vendi.speech.yes_no import normalize


HARDWARE_REPLY = "An operator handles movement and compartments. I can help with the conversation."
FOOD = r"(?:snacks?|drinks?|chips|candy(?: bars?)?|sodas?|water|cookies?|chocolate|pretzels?)"


def guard_social_reply(text, context, transcript):
    """Return a factual replacement only for a concrete shop/status/action claim."""
    product_names = {normalize(item.name) for item in context.inventory}
    product_names.update(normalize(item.id) for item in context.inventory)
    product = "(?:" + "|".join([FOOD, *(re.escape(name) + r"s?" for name in sorted(product_names))]) + ")"
    # "It cost 25 billion dollars" can be an answer about a space program. Only
    # resolve bare pronouns as merchandise when the request refers to this shop.
    local_request = deterministic_intent(transcript, context) in (Intent.CHECK_PRICE, Intent.CHECK_INVENTORY)
    subject = r"^(?:(?:the|our|my) )?" + product
    if local_request:
        subject = r"(?:" + subject + r"|\b(?:it|this|that|they|these|those))"
    for sentence in re.split(r"[.!?;](?:\s|$)", text):
        normalized = normalize(sentence)
        payment = (r"\b(?:(?:your|the) )?(?:payment|refund) (?:has |is |was |has been )?"
                   r"(?:succeeded|successful|complete|completed|confirmed|verified|processed|approved)\b|"
                   r"\b(?:you (?:have |are |were )?(?:paid|charged)|ive (?:charged|refunded) you)\b")
        if re.search(payment, normalized):
            return order_reply("payment", context)
        if re.search(r"\byour (?:order|pickup) (?:is |was |has been )?(?:ready|confirmed|complete|completed|prepared)\b", normalized):
            return order_reply("order", context)
        if re.search(r"\b(?:(?:i|we) (?:have |just )?|ive |weve )(?:opened|closed|unlocked|locked|activated) "
                     r"(?:the |your |my )?(?:lid|compartment|motor|servo)\b|"
                     r"\b(?:the|your) (?:lid|compartment|motor|servo) is (?:open|closed|unlocked|locked|running)\b", normalized):
            return AgentReply(HARDWARE_REPLY)

        # A monetary amount alone could be trivia. A product/deictic subject makes
        # it a vendor price claim; a year or arithmetic answer never does.
        price_subject = subject + r" (?:is|are|costs?|goes? for|will be) "
        amount = (r"(?:only |just )?(?:[$€£]\s*\d+(?:\.\d+)?|"
                  r"(?:\d+(?:\.\d+)?|[a-z]+(?:[ -][a-z]+){0,3})\s+(?:dollars?|cents?|cad|usd)|free)\b")
        if re.search(price_subject + amount, sentence, re.I) or re.search(r"\b(?:our|my) (?:price|prices)\b", normalized):
            return render_intent(Intent.CHECK_PRICE, context, match_product(sentence, context))

        availability = (r"\b(?:i|we) (?:sell|stock|carry)\b|"
                        r"\b(?:(?:i|we) have|ive got|weve got) (?:\w+ ){0,5}" + product + r"\b|" +
                        subject + r" (?:is|are) "
                        r"(?:currently |still )?(?:in stock|available|sold out|out of stock)\b|"
                        r"\b(?:were|we are|im|i am) (?:sold )?out of\b")
        if re.search(availability, normalized):
            return render_intent(Intent.CHECK_INVENTORY, context, match_product(sentence, context))
        # Model-written quantity prose must pass through the same live renderer,
        # including a model that incorrectly labels a stock answer as social.
        quantity = r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|no|a few|plenty|lots)"
        stock_quantity = (subject + r" (?:has|have) " + quantity + r"\b|"
                          r"\b" + quantity + r"(?:\s+\w+){0,5}\s+(?:left|remaining|in stock)\b")
        if (match_product(sentence, context) or local_request) and re.search(stock_quantity, normalized):
            return render_intent(Intent.CHECK_INVENTORY, context,
                                 match_product(sentence, context) or match_product(transcript, context))
    return None
