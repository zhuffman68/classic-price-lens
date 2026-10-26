"""Compact, honest refresh status shared by shop and inventory annotations."""
from .domain import age_text


def reference_status(quote, state, now, ttl):
    if quote is None:
        return {"queued": "lookup queued…", "refreshing": "checking…",
                "retry": "temporarily unavailable"}.get(state, "checking…")
    age = age_text(now - quote.fetched_at)
    if state == "refreshing":
        return f"{age} old • refreshing…"
    if state == "queued":
        return f"{age} old • refresh queued"
    if state == "retry":
        return f"{age} old • retry later"
    if not quote.cache_valid(now, ttl):
        return f"{age} old • refresh needed"
    if quote.price is not None and not quote.fresh(now, ttl):
        if quote.observed_at is None:
            return f"{age} old • report age unknown"
        return f"{age} old • old market reports"
    return age
