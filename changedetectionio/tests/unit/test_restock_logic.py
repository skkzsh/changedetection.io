#!/usr/bin/env python3

# run from dir above changedetectionio/ dir
# python3 -m unittest changedetectionio.tests.unit.test_restock_logic

import unittest
import os

import changedetectionio.processors.restock_diff.processor as restock_diff

# mostly
class TestDiffBuilder(unittest.TestCase):

    def test_logic(self):
        assert restock_diff.is_between(number=10, lower=9, upper=11) == True, "Between 9 and 11"
        assert restock_diff.is_between(number=10, lower=0, upper=11) == True, "Between 9 and 11"
        assert restock_diff.is_between(number=10, lower=None, upper=11) == True, "Between None and 11"
        assert not restock_diff.is_between(number=12, lower=None, upper=11) == True, "12 is not between None and 11"

    def test_itemprop_availability_opengraph_fallback(self):
        """Availability/currency missing from JSON-LD should be filled from OpenGraph
        (Facebook commerce 'product:availability' / 'product:price:currency' meta tags)."""
        html_content = """<!DOCTYPE html>
        <html prefix="og: https://ogp.me/ns# product: https://ogp.me/ns/product#">
        <head>
        <meta property="og:type" content="product">
        <meta property="og:title" content="Some Product">
        <meta property="product:availability" content="in stock">
        <meta property="product:price:currency" content="EUR">
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "Product", "name": "Some Product",
         "offers": {"@type": "Offer", "price": "155.55"}}
        </script>
        </head>
        <body><h1>Some Product</h1></body>
        </html>"""

        value = restock_diff.get_itemprop_availability(html_content)
        assert value.get('price') == 155.55, "price should be found via JSON-LD"
        assert value.get('currency') == 'EUR', "currency should be found via OpenGraph fallback"
        # Normalised the same way a schema.org value is, so that the in-stock matcher
        # (which looks for 'instock') sees it. OpenGraph spells it 'in stock'.
        assert value.get('availability') == 'instock', "availability should be found via OpenGraph fallback and normalised"
        assert any(s in value.get('availability') for s in ['instock', 'instoreonly']), \
            "a product advertised as available must read as in stock, not out of stock"

    def test_price_decimal_comma(self):
        """A decimal comma ("39,99", common for EUR) must not be stripped into 3999"""
        from changedetectionio.processors.restock_diff import Restock
        from changedetectionio.processors.restock_diff.pure_python_extractor import extract_metadata_pure_python, query_price_availability

        for raw, expected in [("39,99", 39.99), ("12.56", 12.56), ("1.299,00", 1299.0), ("1,299.00", 1299.0),
                              ("1,299", 1299.0), ("€ 39,99", 39.99), ("$159", 159.0), ("159", 159.0)]:
            assert Restock().parse_currency(raw) == expected, f"parse_currency({raw!r})"

            microdata = f"""<div itemscope itemtype="http://schema.org/Product"><div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
            <meta itemprop="priceCurrency" content="EUR"><meta itemprop="price" content="{raw}"></div></div>"""
            ld_json = f"""<script type="application/ld+json">{{"@context": "https://schema.org", "@type": "Product", "name": "Some Product",
             "offers": {{"@type": "Offer", "price": "{raw}", "priceCurrency": "EUR"}}}}</script>"""
            microdata_text = f"""<div itemscope itemtype="http://schema.org/Product"><span itemprop="price">{raw}</span></div>"""

            assert restock_diff.get_itemprop_availability(microdata).get('price') == expected, f"microdata {raw!r}"
            assert restock_diff.get_itemprop_availability(ld_json).get('price') == expected, f"JSON-LD {raw!r}"
            assert query_price_availability(extract_metadata_pure_python(ld_json)).get('price') == expected, f"pure python JSON-LD {raw!r}"
            assert query_price_availability(extract_metadata_pure_python(microdata_text)).get('price') == expected, f"pure python microdata text {raw!r}"


class TestPriceFormatting(unittest.TestCase):
    """Price labels follow the page's declared currency and its ISO 4217 decimal places."""

    @staticmethod
    def _format(value, currency=None, locale_name=None):
        from changedetectionio.flask_app import _format_price
        return _format_price(value, currency=currency, locale_name=locale_name)

    def test_jpy_has_no_decimals(self):
        self.assertEqual(self._format(12345.0, 'JPY', 'ja'), '12,345 JPY')
        self.assertEqual(self._format(12345.6, 'JPY', 'ja'), '12,346 JPY')

    def test_trailing_zeroes_are_dropped(self):
        self.assertEqual(self._format(190.0, 'USD', 'en_US'), '190 USD')
        self.assertEqual(self._format(190.5, 'USD', 'en_US'), '190.5 USD')
        self.assertEqual(self._format(190.95, 'USD', 'en_US'), '190.95 USD')

    def test_currency_precision(self):
        self.assertEqual(self._format(5000.0, 'KRW', 'en_US'), '5,000 KRW')
        self.assertEqual(self._format(1.234, 'KWD', 'en_US'), '1.234 KWD')

    def test_locale_grouping_and_separator(self):
        self.assertEqual(self._format(1234567.5, 'EUR', 'ja'), '1,234,567.5 EUR')
        self.assertEqual(self._format(1234567.5, 'EUR', 'de_DE'), '1.234.567,5 EUR')

    def test_missing_currency(self):
        self.assertEqual(self._format(190.5, None, 'en_US'), '190.5')
        self.assertEqual(self._format(190.0, '', 'en_US'), '190')

    def test_non_numeric_values_pass_through(self):
        self.assertEqual(self._format(None, 'JPY', 'ja'), '')
        self.assertEqual(self._format('contact us', 'JPY', 'ja'), 'contact us')


if __name__ == '__main__':
    unittest.main()
