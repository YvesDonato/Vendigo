import unittest

from vendi.speech.spoken_prices import spoken_prices


class SpokenPriceTests(unittest.TestCase):
    def test_prices_are_unambiguous_spoken_amounts(self):
        cases = {
            "KitKat is 1.00 CAD.": "KitKat is one dollar.",
            "$1.00": "one dollar",
            "CAD 1.00": "one dollar",
            "CAD $1.00": "one dollar",
            "C$1.00": "one dollar",
            "CA$1.00": "one dollar",
            "$1.00 CAD": "one dollar",
            "1.00 dollars": "one dollar",
            "2.50 CAD": "two dollars and fifty cents",
            "$1.01": "one dollar and one cent",
            "$0.01": "one cent",
            "$0.50": "fifty cents",
            "$0.00": "zero dollars",
            "$100.00": "one hundred dollars",
            "$1,234.56": "one thousand two hundred thirty-four dollars and fifty-six cents",
            "$1.1": "one dollar and ten cents",
            "One is $1.00; two are $2.00.": "One is one dollar; two are two dollars.",
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(spoken_prices(original), expected)
                self.assertEqual(spoken_prices(expected), expected)

    def test_other_numbers_currencies_and_conversation_are_unchanged(self):
        for text in ("Open for 7 seconds.", "There are 100 left.", "Version 1.00",
                     "It is 2026-09-20.", "2.50 EUR", "US$1.00", "A CAD drawing.",
                     "Hey! What can your snack guide do for you?", "$1.001", "$12,34"):
            with self.subTest(text=text):
                self.assertEqual(spoken_prices(text), text)
