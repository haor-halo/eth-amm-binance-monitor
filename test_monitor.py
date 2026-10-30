import unittest
from decimal import Decimal
from unittest.mock import patch

import monitor


class MonitorTests(unittest.TestCase):
    def test_pool_price_token_order(self):
        raw = "0x" + f"{2**97:064x}"
        self.assertEqual(monitor.pool_price(raw, False), Decimal(4 * 10**12))
        self.assertEqual(monitor.pool_price(raw, True), Decimal(10**12) / 4)

    @patch("monitor.request_json")
    def test_trade_window_expands_and_excludes_future(self, request):
        request.side_effect = [[], [{"T": 9800, "a": 1}, {"T": 10001, "a": 2}]]
        trade = monitor.aligned_trade("ETHUSDC", 10000, 3000)
        self.assertEqual(trade["a"], 1)

    @patch("monitor.request_json")
    def test_truncated_trade_page_is_rejected(self, request):
        request.return_value = [{"T": 9999, "a": i} for i in range(1000)]
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            monitor.aligned_trade("ETHUSDT", 10000, 3000)

    @patch("monitor.request_json", return_value=[])
    def test_missing_trade_remains_missing(self, request):
        self.assertIsNone(monitor.aligned_trade("ETHUSDC", 10000, 3000))


if __name__ == "__main__":
    unittest.main()
