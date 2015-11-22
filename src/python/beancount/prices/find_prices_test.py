"""Tests for price finding routines.
"""
__author__ = "Martin Blais <blais@furius.ca>"

import datetime
import types
import unittest
import pprint

from beancount.prices import find_prices
from beancount.prices.sources import google
from beancount.prices.sources import yahoo
from beancount import loader

PS = find_prices.PriceSource


class TestImportSource(unittest.TestCase):

    def test_import_source_valid(self):
        for name in 'google', 'yahoo':
            module = find_prices.import_source(name)
            self.assertIsInstance(module, types.ModuleType)
        module = find_prices.import_source('beancount.prices.sources.google')
        self.assertIsInstance(module, types.ModuleType)

    def test_import_source_invalid(self):
        with self.assertRaises(ImportError):
            module = find_prices.import_source('non.existing.module')


class TestParseSource(unittest.TestCase):

    def test_source_invalid(self):
        with self.assertRaises(ValueError):
            find_prices.parse_single_source('AAPL')
        with self.assertRaises(ValueError):
            find_prices.parse_single_source('***//--')

        # The module gets imported at this stage.
        with self.assertRaises(ImportError):
            find_prices.parse_single_source('invalid.module.name/NASDAQ:AAPL')

    def test_source_valid(self):
        psource = find_prices.parse_single_source('google/NASDAQ:AAPL')
        self.assertEqual(find_prices.PriceSource(google, 'NASDAQ:AAPL', False),
                         psource)

        psource = find_prices.parse_single_source('beancount.prices.sources.yahoo/AAPL')
        self.assertEqual(
            find_prices.PriceSource(yahoo, 'AAPL', False),
            psource)


class TestParseSourceMap(unittest.TestCase):

    def _clean_source_map(self, smap):
        return {currency: [PS(s[0].__name__, s[1], s[2]) for s in sources]
                for currency, sources in smap.items()}

    def test_source_map_invalid(self):
        with self.assertRaises(ValueError):
            find_prices.parse_source_map('USD')

    def test_source_map_onecur_single(self):
        smap = find_prices.parse_source_map('USD:google/NASDAQ:AAPL')
        self.assertEqual(
            {'USD': [PS('beancount.prices.sources.google', 'NASDAQ:AAPL', False)]},
            self._clean_source_map(smap))

    def test_source_map_onecur_multiple(self):
        smap = find_prices.parse_source_map('USD:google/NASDAQ:AAPL,yahoo/AAPL')
        self.assertEqual(
            {'USD': [PS('beancount.prices.sources.google', 'NASDAQ:AAPL', False),
                     PS('beancount.prices.sources.yahoo', 'AAPL', False)]},
            self._clean_source_map(smap))

    def test_source_map_manycur_single(self):
        smap = find_prices.parse_source_map('USD:google/CURRENCY:GBPUSD '
                                            'CAD:google/CURRENCY:GBPCAD')
        self.assertEqual(
            {'USD': [PS('beancount.prices.sources.google', 'CURRENCY:GBPUSD', False)],
             'CAD': [PS('beancount.prices.sources.google', 'CURRENCY:GBPCAD', False)]},
            self._clean_source_map(smap))

    def test_source_map_manycur_multiple(self):
        smap = find_prices.parse_source_map('USD:google/CURRENCY:GBPUSD,yahoo/GBPUSD '
                                            'CAD:google/CURRENCY:GBPCAD')
        self.assertEqual(
            {'USD': [PS('beancount.prices.sources.google', 'CURRENCY:GBPUSD', False),
                     PS('beancount.prices.sources.yahoo', 'GBPUSD', False)],
             'CAD': [PS('beancount.prices.sources.google', 'CURRENCY:GBPCAD', False)]},
            self._clean_source_map(smap))

    def test_source_map_inverse(self):
        smap = find_prices.parse_source_map('USD:google/^CURRENCY:GBPUSD,yahoo/^GBPUSD')
        self.assertEqual(
            {'USD': [PS('beancount.prices.sources.google', 'CURRENCY:GBPUSD', True),
                     PS('beancount.prices.sources.yahoo', 'GBPUSD', True)]},
            self._clean_source_map(smap))


class TestFromFile(unittest.TestCase):


    @loader.load_doc()
    def setUp(self, entries, _, __):
        """
        2000-01-10 open Assets:US:Investments:QQQ
        2000-01-10 open Assets:CA:Investments:XSP
        2000-01-10 open Assets:Cash
        2000-01-10 open Assets:External
        2000-01-10 open Expenses:Foreign

        2010-01-01 commodity USD

        2010-01-01 commodity QQQ
          name: "PowerShares QQQ Trust, Series 1 (ETF)"
          ticker: "google/NASDAQ:QQQ"
          quote: USD

        2010-01-01 commodity XSP
          name: "iShares S&P 500 Index Fund (CAD Hedged)"
          quote: CAD

        2015-02-06 *
          Assets:Cash                     1505.00 USD
          Assets:External                -1000.00 GBP @ 1.5050 USD

        2015-02-08 price GBP  1.5050 USD
        2015-02-08 price GBP  1.8301 CAD

        2015-04-13 *
          Assets:US:Investments:QQQ             3 QQQ {107.48 USD}
          Assets:Cash

        2015-05-22 *
          Assets:Cash                     1000.00 USD @ 1.2283 CAD
          Assets:External                -1228.30 CAD

        2015-09-04 *
          Assets:US:Investments:QQQ             2 QQQ {101.16 USD}
          Assets:Cash

        2015-11-07 *
          Assets:CA:Investments:XSP             2 XSP {24.28 CAD}
          Assets:Cash

        2015-12-02 *
          Assets:CA:Investments:XSP            -2 XSP {24.28 CAD} @ 27.00 USD
          Assets:Cash

        2015-12-03 price XSP   27.32 USD

        ;; Because neither of these currencies remain, they should not be there.
        2015-06-22 *
          Assets:Cash                         1000.00 EUR @ 140.004 JPY
          Expenses:Foreign                    -140004 JPY

        2015-10-13 *
          Assets:Cash                        -1000.00 EUR @ 140.004 JPY
          Expenses:Foreign                     140004 JPY
        """
        self.entries = entries

    def test_find_currencies_declared(self):
        currencies = find_prices.find_currencies_declared(self.entries, None)
        self.assertEqual({('QQQ', 'USD', 'google/NASDAQ:QQQ'),
                          ('XSP', 'CAD', None)}, currencies)

    def test_find_currencies_converted(self):
        currencies = find_prices.find_currencies_converted(self.entries, None)
        self.assertEqual({('GBP', 'USD'), ('USD', 'CAD'), ('EUR', 'JPY')}, currencies)

        currencies = find_prices.find_currencies_converted(self.entries,
                                                           datetime.date(2015, 5, 1))
        self.assertEqual({('GBP', 'USD')}, currencies)

        currencies = find_prices.find_currencies_converted(self.entries,
                                                           datetime.date(2015, 1, 15))
        self.assertEqual(set(), currencies)

    def test_find_currencies_at_cost(self):
        currencies = find_prices.find_currencies_at_cost(self.entries)
        self.assertEqual({('XSP', 'CAD'), ('QQQ', 'USD')}, currencies)

    def test_find_currencies_priced(self):
        currencies = find_prices.find_currencies_priced(self.entries)
        self.assertEqual({('XSP', 'USD'), ('GBP', 'USD'), ('GBP', 'CAD')}, currencies)

        currencies = find_prices.find_currencies_priced(self.entries,
                                                        datetime.date(2015, 12, 1))
        self.assertEqual({('GBP', 'USD'), ('GBP', 'CAD')}, currencies)

    def test_find_balance_currencies(self):
        currencies = find_prices.find_balance_currencies(self.entries, None)
        self.assertEqual({('QQQ', 'USD'),
                          ('GBP', 'USD'), ('GBP', 'CAD'), ('USD', 'CAD')}, currencies)

        currencies = find_prices.find_balance_currencies(self.entries,
                                                         datetime.date(2015, 12, 1))
        self.assertEqual({('XSP', 'CAD'),
                          ('QQQ', 'USD'), ('GBP', 'USD'), ('GBP', 'CAD'), ('USD', 'CAD')},
                         currencies)

        currencies = find_prices.find_balance_currencies(self.entries,
                                                         datetime.date(2015, 11, 1))
        self.assertEqual({('QQQ', 'USD'),
                          ('GBP', 'USD'), ('GBP', 'CAD'), ('USD', 'CAD')}, currencies)

        currencies = find_prices.find_balance_currencies(self.entries,
                                                         datetime.date(2015, 2, 1))
        self.assertEqual(set(), currencies)
