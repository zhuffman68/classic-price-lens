"""Conservative item identity and price comparisons; no platform dependencies."""
from dataclasses import dataclass
import math
import re
import time

WORLD = "Classic World"
DEFAULT_TTL = 15 * 60
MAX_MARKET_AGE = 24 * 60 * 60


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def key(name):
    name = " ".join(str(name).casefold().replace("’", "'").split())
    return re.sub(r"\s*:\s*", ":", name)


def glyph_key(name):
    # The bundled recognizer reads the small Classic font's y as v (also seen
    # in the upstream Horny Mushroom Cap tooltip fixture). No edit-distance guess.
    return key(name).replace("v", "y")


@dataclass(frozen=True)
class Item:
    game_id: int
    name: str
    equipment: bool = False
    per_set: bool = False
    tier: str | None = None
    cash: bool = False
    nx_price: int | None = None
    nx_count: int = 1
    on_sale: bool | None = None


class Catalog:
    def __init__(self, document, cash_document=None):
        by_id = {}
        self.warning = None
        for row in document.get("items", []) + document.get("scrolls", []):
            if not isinstance(row, dict) or not isinstance(row.get("id"), int) or not row.get("name"):
                continue
            item_id = row["id"]
            by_id[item_id] = Item(item_id, row["name"], row.get("category") == "Equipment",
                                  item_id // 10000 in (207, 233), row.get("tier"))
        for category in (cash_document or {}).get("categories", []):
            for row in category.get("items", []):
                if not isinstance(row, dict) or not isinstance(row.get("id"), int) or not row.get("name"):
                    continue
                nx = row.get("price")
                count = row.get("count", 1)
                by_id[row["id"]] = Item(row["id"], row["name"], row.get("category") == "Equipment",
                                        cash=True, nx_price=int(nx) if number(nx) else None,
                                        nx_count=count if isinstance(count, int) and count > 0 else 1,
                                        on_sale=row.get("on_sale"))
        self.items = list(by_id.values())
        self.names = {}
        self.glyph_names = {}
        for item in self.items:
            self.names.setdefault(key(item.name), []).append(item)
            self.glyph_names.setdefault(glyph_key(item.name), []).append(item)
        self.resolved = {}
        self.preferred = {}

    def candidates(self, visible_name, tier=None):
        name = key(visible_name or "")
        if name in self.names:
            return self.names[name]
        if not re.search(r"(?:\.{2,}|…)$", name):
            return self.glyph_names.get(glyph_key(name), []) if len(name) >= 6 else []
        prefix = re.sub(r"(?:\.{2,}|…)$", "", name).rstrip()
        if len(prefix) < 6:
            return []
        candidates = [i for name_key, items in self.names.items() if name_key.startswith(prefix) for i in items]
        return [i for i in candidates if i.tier and key(i.tier) == key(tier)] if tier else candidates

    def bind_current(self, visible_name, tier, item):
        if item not in self.candidates(visible_name, tier):
            raise ValueError("Provider item does not match visible catalog candidates")
        self.preferred[(key(visible_name), tier)] = item

    def resolve(self, visible_name, tier=None):
        """Only a unique exact name or genuine UI ellipsis prefix; no fuzzy guesses."""
        if not visible_name:
            return None
        name = key(visible_name)
        if (name, tier) in self.preferred:
            return self.preferred[(name, tier)]
        exact = self.names.get(name, [])
        if exact:
            return exact[0] if len(exact) == 1 else None
        if not re.search(r"(?:\.{2,}|…)$", name):
            matches = self.candidates(name, tier)
            return matches[0] if len(matches) == 1 else None
        prefix = re.sub(r"(?:\.{2,}|…)$", "", name).rstrip()
        if len(prefix) < 6:
            return None
        identity = (name, tier)
        if identity in self.resolved:
            return self.resolved[identity]
        candidates = [i for name_key, items in self.names.items() if name_key.startswith(prefix) for i in items]
        if tier:
            candidates = [i for i in candidates if i.tier and key(i.tier) == key(tier)]
        result = candidates[0] if len(candidates) == 1 else None
        if len(self.resolved) >= 512:
            self.resolved.clear()
        self.resolved[identity] = result
        return result


@dataclass(frozen=True)
class Quote:
    game_id: int
    price: float | None
    fetched_at: float
    observed_at: float | None
    sample_count: int
    source: str
    url: str
    period: str
    basis: str = "reported prices (asks + sold)"
    lowest_ask: float | None = None
    low: float | None = None
    high: float | None = None
    per_set: bool = False
    world: str = WORLD
    condition: str = "clean"
    uncertain: bool = False

    def cache_valid(self, now=None, ttl=DEFAULT_TTL):
        now = time.time() if now is None else now
        return 0 <= now - self.fetched_at < ttl

    def fresh(self, now=None, ttl=DEFAULT_TTL):
        now = time.time() if now is None else now
        return (self.world == WORLD and self.cache_valid(now, ttl)
                and self.observed_at is not None and -300 <= now - self.observed_at <= MAX_MARKET_AGE)


@dataclass(frozen=True)
class Verdict:
    label: str
    tone: str
    detail: str
    unit_price: float | None = None
    delta: float | None = None
    net_margin: float | None = None


def compare(item, quantity, mesos, quote, now=None, ttl=DEFAULT_TTL):
    if item is None:
        return Verdict("Unresolved", "muted", "Full item name or scroll tier needed")
    if not number(quantity) or not number(mesos) or quantity != int(quantity) or mesos != int(mesos):
        return Verdict("Unreadable", "muted", "Waiting for a clean price reading")
    unit = float(mesos) if item.per_set else mesos / quantity
    if quote is None or quote.price is None:
        return Verdict("No reference", "muted", quote.basis if quote else "No market reference available", unit)
    if quote.world != WORLD or quote.game_id != item.game_id or quote.per_set != item.per_set or quote.condition != "clean":
        return Verdict("Reference mismatch", "muted", "Item, unit or condition differs", unit)
    if not quote.fresh(now, ttl):
        return Verdict("Expired", "muted", "Refresh needed before comparison", unit)
    if quote.sample_count < 5 or quote.uncertain:
        return Verdict("Thin data", "muted", f"{quote.sample_count} samples; reference only", unit)
    delta = (unit / quote.price - 1) * 100
    net = quote.price * 0.97 - unit  # 3% sale fee shown by the live Classic World shop.
    # User preference: assume equipment is unscrolled, matching the clean reference.
    if unit <= quote.price * 0.8:
        return Verdict("Below reference", "green", f"{abs(delta):.0f}% below • check liquidity", unit, delta, net)
    if unit > quote.price * 1.2:
        return Verdict("Above reference", "red", f"{delta:.0f}% above reference", unit, delta, net)
    return Verdict("Near reference", "blue", f"{delta:+.0f}% versus reference", unit, delta, net)


def age_text(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m"
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h"
