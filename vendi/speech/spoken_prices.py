"""Render explicit dollar amounts for speech without changing application facts."""

import re


_SMALL = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?![\d,]|\.\d)"
_PRICE = re.compile(
    rf"(?<![\w.,])(?:"
    rf"(?:CAD\s*\$?\s*|CA?\$\s*|\$\s*)(?P<prefix>{_AMOUNT})(?:\s+(?:CAD|dollars?)\b)?"
    rf"|(?P<suffix>{_AMOUNT})\s+(?:CAD|dollars?)\b)",
    re.IGNORECASE,
)


def _words(number):
    if number < 20:
        return _SMALL[number]
    if number < 100:
        tens, units = divmod(number, 10)
        return _TENS[tens] + ("-" + _SMALL[units] if units else "")
    for scale, name in ((10**12, "trillion"), (10**9, "billion"),
                        (10**6, "million"), (1000, "thousand"), (100, "hundred")):
        if number >= scale:
            whole, remainder = divmod(number, scale)
            return _words(whole) + " " + name + (" " + _words(remainder) if remainder else "")


def spoken_prices(text):
    """Expand $/CAD/dollar-marked prices; leave unrelated numbers and prose alone."""
    def replace(match):
        amount = (match.group("prefix") or match.group("suffix")).replace(",", "")
        whole, _, fraction = amount.partition(".")
        dollars, cents = int(whole), int(fraction.ljust(2, "0"))
        parts = []
        if dollars or not cents:
            parts.append(_words(dollars) + (" dollar" if dollars == 1 else " dollars"))
        if cents:
            parts.append(_words(cents) + (" cent" if cents == 1 else " cents"))
        return " and ".join(parts)

    return _PRICE.sub(replace, text)
