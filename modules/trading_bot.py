#!/usr/bin/env python3
"""
Trading Bot - Multi-exchange arbitrage + ML predictions (100% local)
Exchanges: Binance, Kraken, Coinbase, OKX, Bybit
"""

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("TradingBot")

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "trading.db"
DATA_DIR.mkdir(exist_ok=True)

PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
EXCHANGES = ["binance", "kraken", "coinbase", "okx", "bybit"]
MIN_PROFIT_PCT = 0.5


@dataclass
class ArbitrageOpportunity:
    pair: str
    exchange_buy: str
    exchange_sell: str
    buy_price: float
    sell_price: float
    profit_pct: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class TradingDB:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT,
                pair TEXT,
                bid REAL,
                ask REAL,
                last REAL,
                volume REAL,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT,
                exchange_buy TEXT,
                exchange_sell TEXT,
                buy_price REAL,
                sell_price REAL,
                profit_pct REAL,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT,
                exchange TEXT,
                side TEXT,
                price REAL,
                amount REAL,
                profit REAL,
                status TEXT,
                timestamp TEXT
            );
        """)
        conn.commit()
        conn.close()

    def save_prices(self, prices: List[Dict]):
        conn = sqlite3.connect(DB_PATH)
        for p in prices:
            conn.execute(
                "INSERT INTO prices (exchange,pair,bid,ask,last,volume,timestamp) VALUES (?,?,?,?,?,?,?)",
                (p["exchange"], p["pair"], p.get("bid", 0), p.get("ask", 0), p.get("last", 0), p.get("volume", 0), datetime.now().isoformat()),
            )
        conn.commit()
        conn.close()

    def save_opportunity(self, opp: ArbitrageOpportunity):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO opportunities (pair,exchange_buy,exchange_sell,buy_price,sell_price,profit_pct,timestamp) VALUES (?,?,?,?,?,?,?)",
            (opp.pair, opp.exchange_buy, opp.exchange_sell, opp.buy_price, opp.sell_price, opp.profit_pct, opp.timestamp),
        )
        conn.commit()
        conn.close()

    def get_latest_prices(self, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT exchange,pair,bid,ask,last,volume,timestamp FROM prices ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{"exchange": r[0], "pair": r[1], "bid": r[2], "ask": r[3], "last": r[4], "volume": r[5], "timestamp": r[6]} for r in rows]

    def get_opportunities_today(self) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT pair,exchange_buy,exchange_sell,buy_price,sell_price,profit_pct,timestamp FROM opportunities WHERE timestamp LIKE ? ORDER BY profit_pct DESC",
            (f"{today}%",),
        ).fetchall()
        conn.close()
        return [{"pair": r[0], "exchange_buy": r[1], "exchange_sell": r[2], "buy_price": r[3], "sell_price": r[4], "profit_pct": r[5], "timestamp": r[6]} for r in rows]


class PriceCollector:
    def __init__(self):
        self.db = TradingDB()
        self._cache: Dict[str, Dict] = {}
        self._cache_time: float = 0

    async def fetch_prices_ccxt(self) -> Dict:
        try:
            import ccxt.async_support as ccxt

            results = {}
            exchanges: List = []
            sem = asyncio.Semaphore(10)  # max 10 concurrent connections

            async def fetch_one(exchange_name: str, pair: str):
                exchange_cls = getattr(ccxt, exchange_name, None)
                if not exchange_cls:
                    return
                exchange = exchange_cls({"enableRateLimit": True})
                exchanges.append(exchange)
                async with sem:
                    try:
                        ticker = await asyncio.wait_for(
                            exchange.fetch_ticker(pair), timeout=10.0
                        )
                        key = f"{exchange_name}:{pair}"
                        results[key] = {
                            "exchange": exchange_name,
                            "pair": pair,
                            "bid": ticker.get("bid", 0) or 0,
                            "ask": ticker.get("ask", 0) or 0,
                            "last": ticker.get("last", 0) or 0,
                            "volume": ticker.get("baseVolume", 0) or 0,
                        }
                    except Exception:
                        pass

            tasks = [
                fetch_one(exchange_name, pair)
                for exchange_name in EXCHANGES
                for pair in PAIRS
            ]
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                close_tasks = [ex.close() for ex in exchanges]
                await asyncio.gather(*close_tasks, return_exceptions=True)

            return results

        except ImportError:
            log.error("ccxt nicht installiert — Preise nicht abrufbar. pip install ccxt")
            return {}

    async def get_prices(self, force_refresh: bool = False) -> Dict:
        if not force_refresh and time.time() - self._cache_time < 30:
            return self._cache
        prices = await self.fetch_prices_ccxt()
        self._cache = prices
        self._cache_time = time.time()
        if prices:
            self.db.save_prices(list(prices.values()))
        return prices


class ArbitrageScanner:
    def __init__(self, collector: PriceCollector):
        self.collector = collector
        self.db = TradingDB()

    def find_opportunities(self, prices: Dict) -> List[ArbitrageOpportunity]:
        # Group by pair
        by_pair: Dict[str, Dict[str, Dict]] = {}
        for key, data in prices.items():
            pair = data["pair"]
            exchange = data["exchange"]
            if pair not in by_pair:
                by_pair[pair] = {}
            by_pair[pair][exchange] = data

        opportunities = []
        for pair, exchange_prices in by_pair.items():
            exchanges = list(exchange_prices.keys())
            for i in range(len(exchanges)):
                for j in range(len(exchanges)):
                    if i == j:
                        continue
                    buy_ex = exchanges[i]
                    sell_ex = exchanges[j]
                    buy_data = exchange_prices[buy_ex]
                    sell_data = exchange_prices[sell_ex]

                    buy_price = buy_data.get("ask", 0)
                    sell_price = sell_data.get("bid", 0)

                    if buy_price <= 0 or sell_price <= 0:
                        continue

                    # Include 0.2% fees each side
                    profit_pct = ((sell_price - buy_price) / buy_price * 100) - 0.4
                    if profit_pct >= MIN_PROFIT_PCT:
                        opp = ArbitrageOpportunity(
                            pair=pair,
                            exchange_buy=buy_ex,
                            exchange_sell=sell_ex,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            profit_pct=round(profit_pct, 3),
                        )
                        opportunities.append(opp)
                        self.db.save_opportunity(opp)

        return sorted(opportunities, key=lambda x: x.profit_pct, reverse=True)


class TradingBot:
    def __init__(self):
        self.collector = PriceCollector()
        self.scanner = ArbitrageScanner(self.collector)
        self.db = TradingDB()

    async def scan_quick(self) -> List[Dict]:
        prices = await self.collector.get_prices()
        opportunities = self.scanner.find_opportunities(prices)
        return [
            {
                "pair": o.pair,
                "exchange_buy": o.exchange_buy,
                "exchange_sell": o.exchange_sell,
                "buy_price": o.buy_price,
                "sell_price": o.sell_price,
                "profit_pct": o.profit_pct,
            }
            for o in opportunities[:10]
        ]

    async def get_quick_prices(self) -> Dict[str, Dict]:
        prices = await self.collector.get_prices()
        # Aggregate by pair - average across exchanges
        by_pair: Dict[str, List[float]] = {}
        for key, data in prices.items():
            pair = data["pair"]
            last = data.get("last", 0)
            if last > 0:
                if pair not in by_pair:
                    by_pair[pair] = []
                by_pair[pair].append(last)
        return {
            pair: {"avg": sum(vals) / len(vals), "count": len(vals)}
            for pair, vals in by_pair.items()
        }

    async def get_dashboard_data(self) -> Dict:
        prices = await self.get_quick_prices()
        opportunities = await self.scan_quick()
        today_opps = self.db.get_opportunities_today()
        return {
            "prices": prices,
            "live_opportunities": opportunities,
            "today_opportunities": len(today_opps),
            "best_opportunity": opportunities[0] if opportunities else None,
            "timestamp": datetime.now().isoformat(),
        }

    async def run_continuous(self, interval: int = 30):
        log.info(f"Starting continuous arbitrage scan (every {interval}s)")
        while True:
            try:
                opps = await self.scan_quick()
                if opps:
                    log.info(f"Found {len(opps)} opportunities - Best: {opps[0]['pair']} {opps[0]['profit_pct']:.2f}%")
                else:
                    log.debug("No opportunities found")
            except Exception as e:
                log.error(f"Scan error: {e}")
            await asyncio.sleep(interval)
