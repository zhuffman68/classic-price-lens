"""Public Classic World HTTP data and a bounded SQLite cache. Never uploads pixels."""
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time

from .domain import Catalog, WORLD
from .http_json import get_json

CATALOG_URL = "https://osmsdataexplorer.com/data/current/items.json"
CASH_CATALOG_URL = "https://osmsdataexplorer.com/data/current/cash_shop.json"


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


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
