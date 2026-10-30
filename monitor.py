#!/usr/bin/env python3
"""Compare Uniswap V3 block-end prices with timestamp-aligned Binance trades."""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from decimal import Decimal, getcontext

getcontext().prec = 60
POOLS = {
    "ETHUSDC": ("0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640", True),
    "ETHUSDT": ("0x11b815efB8f581194ae79006d24E0d814B7697F6", False),
}
BINANCE = "https://api.binance.com/api/v3/aggTrades"


def request_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "eth-amm-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def rpc(url, method, params):
    result = request_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in result:
        raise RuntimeError("RPC returned an error")
    return result["result"]


def pool_price(raw, inverted):
    sqrt_price = Decimal(int(raw[2:66], 16)) / Decimal(2**96)
    if not sqrt_price:
        raise ValueError("empty pool price")
    ratio = sqrt_price * sqrt_price
    return Decimal(10**12) / ratio if inverted else Decimal(10**12) * ratio


def aligned_trade(symbol, block_ms, max_age_ms):
    # Use a narrow interval and expand only when empty. Never silently accept a
    # full page: Binance returns the oldest 1000 results in the requested range.
    width = min(1000, max_age_ms)
    while True:
        params = {"symbol": symbol, "startTime": block_ms - width, "endTime": block_ms, "limit": 1000}
        trades = request_json(BINANCE + "?" + urllib.parse.urlencode(params))
        if not isinstance(trades, list):
            raise RuntimeError("unexpected Binance response")
        if len(trades) >= 1000:
            raise RuntimeError("Binance trade window truncated; no aligned price")
        eligible = [x for x in trades if x["T"] <= block_ms]
        if eligible:
            return max(eligible, key=lambda x: (x["T"], x["a"]))
        if width >= max_age_ms:
            return None
        width = min(width * 2, max_age_ms)


def timestamp(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def snapshot(url, block_number, max_age_ms):
    block = rpc(url, "eth_getBlockByNumber", [block_number, False])
    if not block:
        raise RuntimeError("block unavailable")
    block_ms = int(block["timestamp"], 16) * 1000
    result = {"block_number": int(block_number, 16), "block_hash": block["hash"], "block_timestamp": timestamp(block_ms), "read_at": timestamp(int(time.time() * 1000)), "pairs": {}}
    for symbol, (address, inverted) in POOLS.items():
        try:
            raw = rpc(url, "eth_call", [{"to": address, "data": "0x3850c7bd"}, {"blockHash": block["hash"], "requireCanonical": True}])
            amm = pool_price(raw, inverted)
            trade = aligned_trade(symbol, block_ms, max_age_ms)
            if trade is None:
                raise RuntimeError("no Binance trade within maximum age")
            price = Decimal(trade["p"])
            if price <= 0:
                raise ValueError("invalid Binance trade price")
            result["pairs"][symbol] = {"pool": address, "amm_price": str(amm), "binance_trade_price": str(price), "binance_trade_timestamp": timestamp(trade["T"]), "trade_age_ms": block_ms - trade["T"], "binance_agg_trade_id": trade["a"], "amm_vs_binance_bps": str((amm / price - 1) * 10000)}
        except Exception as exc:
            # Avoid printing RPC URLs, which may contain API keys.
            result["pairs"][symbol] = {"pool": address, "error": type(exc).__name__ + ": " + (str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "request failed")}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=os.environ.get("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com"), help="Ethereum RPC URL (or ETH_RPC_URL)")
    parser.add_argument("--once", action="store_true", help="print one snapshot and exit")
    parser.add_argument("--poll-seconds", type=float, default=1, help="block polling interval (default: 1)")
    parser.add_argument("--max-trade-age-ms", type=int, default=30000, help="maximum age before the block timestamp (default: 30000)")
    args = parser.parse_args()
    if args.poll_seconds <= 0 or args.max_trade_age_ms <= 0:
        parser.error("poll interval and maximum trade age must be positive")
    last = None
    while True:
        try:
            number = rpc(args.rpc_url, "eth_blockNumber", [])
            if number != last:
                result = snapshot(args.rpc_url, number, args.max_trade_age_ms)
                print(json.dumps(result, separators=(",", ":")), flush=True)
                last = number
                if args.once:
                    return 1 if any("error" in x for x in result["pairs"].values()) else 0
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__, "message": "snapshot request failed", "read_at": timestamp(int(time.time() * 1000))}), file=sys.stderr, flush=True)
            if args.once:
                return 1
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
