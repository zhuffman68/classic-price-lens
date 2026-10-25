"""Public Classic World HTTP data and a bounded SQLite cache. Never uploads pixels."""
from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
import urllib.parse
import urllib.request
import urllib.error

from .domain import Catalog, Quote, WORLD, key, number

API = "https://meowdb.com/msclassic/api/"
CATALOG_URL = "https://osmsdataexplorer.com/data/current/items.json"
CASH_CATALOG_URL = "https://osmsdataexplorer.com/data/current/cash_shop.json"
UA = "ClassicPriceLens/0.1 (personal, screen-only Classic World price viewer)"
MAX_RESPONSE = 8 * 1024 * 1024


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as response:
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError("Data response exceeds size limit")
    return json.loads(body)


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS entries (world TEXT, kind TEXT, identity TEXT, saved REAL, payload TEXT, PRIMARY KEY(world, kind, identity))")
            db.execute("DELETE FROM entries WHERE saved < ?", (time.time() - 7 * 86400,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, identity, data, saved=None):
        saved = time.time() if saved is None else saved
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?)",
                       (WORLD, kind, str(identity), saved, json.dumps(data, allow_nan=False)))
            db.execute("DELETE FROM entries WHERE rowid IN (SELECT rowid FROM entries ORDER BY saved DESC LIMIT -1 OFFSET 6000)")

    def get(self, kind, identity, max_age=None):
        with self.connect() as db:
            row = db.execute("SELECT saved, payload FROM entries WHERE world=? AND kind=? AND identity=?",
                             (WORLD, kind, str(identity))).fetchone()
        if row and (max_age is None or 0 <= time.time() - row[0] < max_age):
            return json.loads(row[1])
        return None

    def save_quote(self, quote):
        if quote.world != WORLD:
            raise ValueError("Only Classic World market data is accepted")
        self.put("quote:" + quote.source, quote.game_id, asdict(quote), quote.fetched_at)

    def quote(self, item_id):
        quotes = []
        for source in ("NiaMeowDB", "MesoWatch"):
            raw = self.get("quote:" + source, item_id)
            if raw:
                quotes.append(Quote(**raw))
        return max(quotes, key=lambda q: q.fetched_at, default=None)


def load_catalog(cache):
    document = cache.get("catalog", "osms", 86400)
    if document is None:
        try:
            document = get_json(CATALOG_URL)
            if not isinstance(document, dict) or not document.get("items") or not isinstance(document.get("scrolls"), list):
                raise ValueError("Classic World catalog format changed")
            cache.put("catalog", "osms", document)
        except Exception:
            document = cache.get("catalog", "osms")
            if document is None:
                raise
    cash = cache.get("catalog", "osms-cash", 86400)
    warning = None
    if cash is None:
        try:
            cash = get_json(CASH_CATALOG_URL)
            if not isinstance(cash, dict) or not isinstance(cash.get("categories"), list) or not cash["categories"]:
                raise ValueError("Classic World cash catalog format changed")
            cache.put("catalog", "osms-cash", cash)
        except Exception as error:
            cash = cache.get("catalog", "osms-cash")
            if cash is None:
                warning = f"NX catalog unavailable: {error}"
    catalog = Catalog(document, cash)
    catalog.warning = warning
    return catalog


def parse_summary(item, summary, provider_id, fetched_at):
    if not isinstance(summary, dict) or summary.get("itemId") != provider_id or summary.get("condition") != "clean":
        raise ValueError("Market response identity or condition mismatch")
    daily = summary.get("last24h") or {}
    count = daily.get("count", 0)
    use_daily = isinstance(count, int) and count >= 5 and number(daily.get("median")) is not None
    price = number(daily.get("median")) if use_daily else number(summary.get("usual"))
    if price is None and number(daily.get("median")) is not None and isinstance(count, int) and count > 0:
        use_daily = True
        price = number(daily["median"])
    fallback_count = summary.get("priceChecks", 0) + summary.get("finishedTrades", 0)
    return Quote(item.game_id, price, fetched_at, timestamp(summary.get("newestPriceAt")),
                 int(count if use_daily else fallback_count), "NiaMeowDB",
                 f"https://meowdb.com/msclassic/item-db/{provider_id}#free-market",
                 "24h" if use_daily else f"{summary.get('windowDays', 14)}d",
                 basis="reported prices (asks + sold)" if price is not None else "No reported market price from this source",
                 lowest_ask=number(summary.get("cheapestSell")),
                 low=number(daily.get("low")) if use_daily else None,
                 high=number(daily.get("high")) if use_daily else None, per_set=item.per_set)


class MeowProvider:
    def __init__(self, cache):
        self.cache = cache

    def resolve_id(self, item):
        cached = self.cache.get("meow-id", item.game_id, 86400)
        if cached:
            return cached["id"]
        # The site's database row ID is different from the game's item ID.
        data = get_json(API + "items?" + urllib.parse.urlencode({"search": item.name}))
        matches = [row for row in data.get("items", []) if str(row.get("iconKey")) == str(item.game_id)
                   and key(row.get("name", "")) == key(item.name)]
        if len(matches) != 1:
            raise ValueError("No unique Classic World provider ID matches the item")
        provider_id = matches[0]["id"]
        self.cache.put("meow-id", item.game_id, {"id": provider_id})
        return provider_id

    def resolve_name(self, visible_name, candidates):
        """Narrow duplicate catalog names using the provider's current Classic catalog."""
        allowed = {str(item.game_id): item for item in candidates}
        cached = self.cache.get("meow-name", key(visible_name), 86400)
        if cached and str(cached["game_id"]) in allowed:
            return allowed[str(cached["game_id"])]
        search = visible_name.rstrip(". …")
        if candidates and len({key(item.name) for item in candidates}) == 1:
            search = candidates[0].name
        data = get_json(API + "items?" + urllib.parse.urlencode({"search": search}))
        if data.get("hasMore"):
            raise ValueError("Several current item versions match; need a more specific name")
        matches = [(allowed[str(row.get("iconKey"))], row["id"]) for row in data.get("items", [])
                   if str(row.get("iconKey")) in allowed
                   and key(row.get("name", "")) == key(allowed[str(row.get("iconKey"))].name)]
        if len(matches) != 1:
            raise ValueError("Several current item versions match; no unique price reference")
        item, provider_id = matches[0]
        self.cache.put("meow-id", item.game_id, {"id": provider_id})
        self.cache.put("meow-name", key(visible_name), {"game_id": item.game_id})
        return item

    def fetch(self, item):
        provider_id = self.resolve_id(item)
        query = urllib.parse.urlencode({"itemId": provider_id, "condition": "clean"})
        try:
            data = get_json(API + "item-market-summary?" + query)
        except urllib.error.HTTPError as error:
            if error.code != 400:
                raise
            try:
                rejection = json.loads(error.read(4096))
            except (ValueError, TypeError):
                raise ValueError(f"{item.name}: price source rejected this lookup (HTTP 400)") from error
            finally:
                error.close()
            if rejection.get("code") != "fm_not_tradeable":
                raise ValueError(f"{item.name}: {rejection.get('error', 'price source rejected this lookup')}") from error
            # This is the source's coverage rule, not proof the game disallows a trade.
            quote = Quote(item.game_id, None, time.time(), None, 0, "NiaMeowDB",
                          f"https://meowdb.com/msclassic/item-db/{provider_id}#free-market", "no data",
                          basis="Price source does not cover this item's market trades", per_set=item.per_set, uncertain=True)
            self.cache.save_quote(quote)
            return quote
        quote = parse_summary(item, data, provider_id, time.time())
        self.cache.save_quote(quote)
        return quote


def import_mesowatch(path, cache):
    """Read an already obtained original MesoWatch list/market file, with its publish time."""
    with Path(path).open(encoding="utf-8") as stream:
        doc = json.load(stream)
    published = timestamp(doc.get("generated_at"))
    if doc.get("market") != WORLD or doc.get("preview") or not published or published > time.time() + 300:
        raise ValueError("Expected a dated Classic World MesoWatch snapshot, not a closed-test market")
    if not isinstance(doc.get("items"), list):
        raise ValueError("Snapshot has no item list")
    count = 0
    for row in doc["items"]:
        raw_id = str(row.get("id", ""))
        if not raw_id.startswith(("basil:", "cash:")):
            continue
        try:
            item_id = int(raw_id.split(":", 1)[1])
        except ValueError:
            continue
        if number(row.get("price")) is None:
            continue
        quote = Quote(item_id, float(row["price"]), min(time.time(), published), published,
                      int(row.get("sold") or 0), "MesoWatch", "https://meso.watch/", "site window",
                      basis="observed shop sales", per_set=row.get("unitBasis") == "set",
                      low=number(row.get("p25")), high=number(row.get("p75")),
                      uncertain=bool(row.get("lowData", True) or row.get("scrolledOnly")))
        cache.save_quote(quote)
        count += 1
    return count
