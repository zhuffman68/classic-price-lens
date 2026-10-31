"""Per-item sale age and explicit stale/update status for game annotations."""
from .domain import MAX_SNAPSHOT_AGE, age_text


def reference_status(quote, state, now, ttl):
    if quote is None:
        return {"queued": "lookup queued…", "refreshing": "checking…",
                "retry": "temporarily unavailable"}.get(state, "checking…")
    label='Last sale' if quote.source=='MesoWatch' else 'Latest report'
    observed_age=now-quote.observed_at if quote.observed_at is not None else None
    age=(f'{label} {age_text(max(0,observed_age))} ago'
         if observed_age is not None and observed_age>=-300 else f'{label} unknown')
    if state == "refreshing":
        return f"{age} • refreshing…"
    if state == "queued":
        return f"{age} • refresh queued"
    if state == "retry":
        return f"{age} • retry later"
    if not quote.cache_valid(now, ttl):
        if quote.published_at is not None and now >= quote.published_at + MAX_SNAPSHOT_AGE:
            return f"{age} • source snapshot old"
        return f"{age} • refresh needed"
    if quote.price is not None and not quote.fresh(now, ttl):
        return f"{age} • old market reports" if observed_age is not None and observed_age>86400 else f"{age} • report age unknown"
    return age
