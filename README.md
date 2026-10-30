# Ethereum AMM vs Binance monitor

Monitor Ethereum Uniswap V3 WETH/USDC and WETH/USDT pools against Binance spot trades. Each JSON line represents one observed block and includes the pool's end-of-block marginal price and the most recent Binance aggregate trade at or before that block's timestamp.

## Run

Requires Python 3.10+ and network access. No packages or API keys are required.

```sh
python3 monitor.py --once
python3 monitor.py
python3 monitor.py > snapshots.jsonl
ETH_RPC_URL=https://your-ethereum-rpc python3 monitor.py
```

Use `--poll-seconds` to change the polling interval and `--max-trade-age-ms` to limit trade staleness. `--once` exits nonzero if either pair fails. In continuous mode, pair failures are reported in JSON, and network failures on stderr. Unavailable prices are never replaced with zero. RPC must support EIP-1898 block-hash `eth_call` and historical state for the observed block.

## Method

- Query the latest Ethereum block and pin each `slot0` read to its canonical block hash. Decode `sqrtPriceX96`, accounting for token order and decimals.
- Query Binance `aggTrades` for the last trade at or before the block timestamp, initially within one second, expanding only as needed. A full 1,000-trade page is rejected as potentially truncated. Report the timestamp, age and aggregate trade ID.
- Calculate `(AMM price / Binance trade price - 1) * 10000` in bps. Positive means AMM is higher.

This compares the block-end pool state with a trade before the block timestamp, not historical Binance bid/ask mid. Block timestamps do not give individual transaction execution times; the reported difference is not executable arbitrage profit. The pool price excludes fees, slippage, gas and trade size. Polling can skip blocks and a later reorganization can invalidate a previously printed observation. No results are persisted unless output is redirected.

Pools: [WETH/USDC 0.05%](https://etherscan.io/address/0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640), [WETH/USDT 0.05%](https://etherscan.io/address/0x11b815efB8f581194ae79006d24E0d814B7697F6). Binance endpoints can be region-restricted.
