"""Local, atomic Classic World price snapshots. No browser or capture dependencies."""
from dataclasses import asdict
import json
import re
import time

from .data import timestamp
from .domain import Quote, WORLD, key, number

SNAPSHOT_TTL = 3600


def parse_snapshot(document, checked_at=None):
    checked_at = time.time() if checked_at is None else checked_at
    if (not isinstance(document, dict) or document.get("market") != WORLD
            or document.get("preview") is not False or document.get("version") != 2
            or document.get("kind") != "list"):
        raise ValueError("Expected the live Classic World price list")
    published = timestamp(document.get("generated_at"))
    if not published or published > checked_at + 300:
        raise ValueError("Invalid market publication time")
    source_rows = document.get("items")
    if not isinstance(source_rows, list) or not 1 <= len(source_rows) <= 20000:
        raise ValueError("Invalid market item list")
    rows = {}
    excluded_aliases = 0
    for row in source_rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid market item")
        identity = row.get("id", "")
        match = re.fullmatch(r"(?:basil|cash):(\d{8})", identity) if isinstance(identity, str) else None
        name = row.get("name")
        catalog_id = row.get("catalogId", identity)
        if (not match or not isinstance(catalog_id, str)
                or not re.fullmatch(r"(?:basil|cash):\d{8}", catalog_id)
                or not isinstance(name, str) or not 1 <= len(name) <= 200):
            raise ValueError("Invalid market item identity")
        # The source can include an alias whose listing ID differs from its
        # catalog ID. Neither identity is proven for our exact-ID prices, so
        # omit that row without blocking unrelated, independently valid rows.
        if catalog_id != identity:
            excluded_aliases += 1
            continue
        game_id = int(match[1])
        if game_id in rows:
            raise ValueError("Duplicate market item identity")
        count = row.get("priceSales", 0)
        count = count if type(count) is int and 0 <= count <= 100000000 else 0
        price = number(row.get("price"))
        period = row.get("priceBasis")
        unit = row.get("unitBasis")
        # Lifetime sales, NX retail values and unknown units are never prices.
        uncertain = (row.get("lowData") is not False or bool(row.get("scrolledOnly"))
                     or period not in ("24h", "last10") or unit not in ("item", "set"))
        quote = Quote(game_id, price, checked_at, timestamp(row.get("lastSold")), count,
                      "MesoWatch", "https://meso.watch/", "last 10 sales" if period == "last10" else period or "unknown window",
                      basis="observed shop sales", low=number(row.get("p25")),
                      high=number(row.get("p75")), per_set=unit == "set",
                      uncertain=uncertain, published_at=published)
        rows[game_id] = {"name": name, "unit": unit, "quote": asdict(quote)}
    if not rows:
        raise ValueError("No exact market item identities")
    meta = {"checked_at": checked_at, "published_at": published, "rows": len(rows),
            "priced": sum(row["quote"]["price"] is not None for row in rows.values())}
    if excluded_aliases:
        meta["excluded_aliases"] = excluded_aliases
    return meta, rows


class SnapshotStore:
    def __init__(self, cache):
        self.cache = cache
        with cache.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS market_snapshot_meta (world TEXT PRIMARY KEY, payload TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS market_snapshot_rows (world TEXT, game_id INTEGER, payload TEXT, PRIMARY KEY(world,game_id))")
        self.reload()

    def reload(self):
        with self.cache.connect() as db:
            meta = db.execute("SELECT payload FROM market_snapshot_meta WHERE world=?", (WORLD,)).fetchone()
            rows = db.execute("SELECT game_id,payload FROM market_snapshot_rows WHERE world=?", (WORLD,)).fetchall()
        self.meta = json.loads(meta[0]) if meta else None
        self.rows = {identity: json.loads(payload) for identity, payload in rows}

    def save(self, document, checked_at=None):
        meta, rows = parse_snapshot(document, checked_at)
        if self.meta and meta["published_at"] < self.meta["published_at"]:
            raise ValueError("Market snapshot is older than the saved copy")
        # Validate everything first, then replace the complete generation in one
        # transaction. A failed download/parse/write leaves the last good copy.
        encoded = [(WORLD, identity, json.dumps(row, allow_nan=False)) for identity, row in rows.items()]
        with self.cache.connect() as db:
            db.execute("DELETE FROM market_snapshot_rows WHERE world=?", (WORLD,))
            db.executemany("INSERT INTO market_snapshot_rows VALUES (?,?,?)", encoded)
            db.execute("INSERT OR REPLACE INTO market_snapshot_meta VALUES (?,?)",
                       (WORLD, json.dumps(meta, allow_nan=False)))
        self.meta, self.rows = meta, rows
        return meta

    def quote(self, item):
        row = self.rows.get(item.game_id)
        if (not row or key(row["name"]) != key(item.name) or row["unit"] not in ("item", "set")
                or (row["unit"] == "set") != item.per_set):
            return None
        quote = Quote(**row["quote"])
        return quote if quote.price is not None else None

    def identify(self, candidates):
        if not self.meta or not 0 <= time.time() - self.meta["published_at"] < SNAPSHOT_TTL:
            return None
        matches = [item for item in candidates if (row := self.rows.get(item.game_id))
                   and key(row["name"]) == key(item.name)]
        return matches[0] if len(matches) == 1 else None
