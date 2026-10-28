# Price latency

## Current behavior: v0.13.2

Prices are local reads from a single MesoWatch full-market snapshot. It refreshes on launch and at the selected 5/15/30/60-minute interval. Individual price API requests, provider-ID lookups, early per-item refresh and their worker queues have been removed. Missing items remain unpriced.

Saved data appears immediately. A successful full refresh replaces the generation atomically; failed updates retain the original check/publication/report ages. Expired data has no deal colors. The larger card's latest observed-sale time is separate from the median reference and snapshot publication.

The updater now uses a small native system-web-view helper: WebKitGTK on Linux and the production WebView2 runtime on Windows. It exits after each update and needs no installed browser application or DevTools connection. A live Linux refresh downloaded and validated 1,917 rows (1,333 positive prices) in 2.322 seconds. This background work does not delay a saved item lookup. Timings vary with the network and machine load.

The helper pipe is limited to one UTF-8 JSON object of at most 8 MiB. Its own deadline is 20 seconds; the parent permits 25 seconds, then terminates it and escalates after 800 ms. Cancelled or late output cannot replace the saved generation. A self-test loads local HTML without network access.

Screen capture, OCR and rendering are separate costs. The Windows client drains local frame packets and keeps only the newest completed frame. Live samples after this fix had frame ages around 0.17–0.26 seconds; an example read took about 293 ms. A missing-price OCR retry is limited to the detected shop, requires two strict readings to agree, and caches unchanged patches. These are observations under VM/host load, not latency guarantees.

The historical investigation below describes retired per-item behavior and earlier measurements.

---

# Price lookup timing

Measured on 2026-10-27 against the current NiaMeowDB Classic World API. This is a small diagnostic sample, not a service benchmark or a latency guarantee.

| Request | Connection setup | Wait for response headers | Total |
| --- | ---: | ---: | ---: |
| Resolve Weighted Earrings to a provider ID | 184 ms | 3,384 ms | 3,568 ms |
| First price summary, same connection | reused | 906 ms | 906 ms |
| Repeated summary, same connection | reused | 52 ms | 52 ms |

The JSON bodies were only 341–460 bytes. Most of the delay was waiting for headers, which includes network and source processing time. The faster repeated response also reflects upstream warming/caching, so its improvement cannot be attributed solely to connection reuse. An uncached item's identity lookup can dominate the full lookup. Already-known items usually skip that lookup through the existing daily provider-ID cache.

## Implemented

- Reuse HTTPS connections inside the existing three worker threads, with a shared verifying TLS context. Expire idle connections after 30 seconds and cap each thread at four hosts. This removes repeated connection setup when several items are checked in quick succession. Existing system/user proxies retain the urllib path.
- Retry one stale reused connection after a disconnect. Timeouts and API errors retain the existing backoff; successful, empty, unsupported and old-data responses retain their full selected cache lifetime.
- Search the local Classic World catalog while typing. An explicit selection adds one manual lookup to the existing bounded scheduler. A shared name is resolved through the current provider before its price is requested; name resolution and prices still coalesce with screen-driven requests.
- Keep an existing quote visible, including its actual check/report ages, during refresh. Manual search uses the same persisted cache as overlays, and leaving the Search tab cancels queued manual demand. No polling of all search suggestions or the wider market is introduced.

## Further options

A documented batch endpoint or provider-maintained ID catalog could reduce first-store round trips. Those require cooperation or a published interface from the source; the current summary response is per item. Changing the reference source also requires comparing Classic World item identity, NX coverage, clean-equipment conditions, timestamps and sample quality. Increasing concurrency alone does not remove a slow origin response and can place more load on the service.

The full application still uses OS screen capture only. Price requests contain catalog/item information, never screenshots, EXP readings or character/session history.

## v0.7.0 improvements and measured boundary

Obsolete direct HTTPS sockets can be interrupted, so a newly opened page does not wait for irrelevant responses. A local held-response test verifies cancellation in under 500 ms without another request. The bounded three-worker pool, quote TTLs and error/coverage cooldowns remain in force. Configured-proxy urllib requests retain their timeout and may not interrupt before response headers.

A daily public MesoWatch ID index can extend an exact name/game-ID mapping previously validated by NiaMeowDB. It never supplies identity for a new item. An unchanged fresh index can reuse the original proof for up to seven days; changed or missing proof falls back to normal matching. Index enrolment does not change its provider-check timestamp. The sampled index matched 153 checked mappings, omitted 45 and contradicted none. This reduces recurring identification requests independently of price freshness.

In a synthetic captured-page test, real OCR and Qt classified five cache-backed shop rows in 187.6/224.9/11.2/32.2 ms over four reads, including a moved shop, with EXP reads enabled and zero price API calls. OS capture and compositor presentation are excluded. Uncached source responses can still take seconds. A moved crop that contains names but clips prices is now retried over the full area immediately.

Price cards update in place. Short text/section/tab transitions do not wait for every page request, and fresh deal colors publish independently as quotes arrive. Unknown, stale, unsupported or thin-data entries remain neutral.

The whole-market cache below avoids per-item round trips for matching entries. Items absent from it retain the bounded fallback scheduler.

### Hourly full-price cache investigation

An isolated, ordinary browser loaded the current Classic World list (`preview=false`, format v2): 1,865 item rows, 1,277 positive prices, 179 cash-catalog rows and 176 positive cash prices. The initial list transferred 258,014 bytes and decoded to 1,990,161 bytes in a 168 ms browser sample. The list covered White Jeans, Sailor Outfit, Blue Hawkeye and Work Gloves. Normal and browser-compatible direct HTTP clients both returned 403, including with a same-site Referer. Browser access succeeded.

The full-cache updater reads saved data immediately, refreshes asynchronously once on every launch, then about hourly while running (slightly earlier before a valid publication expires). Already-old publications do not trigger a rapid refresh loop. One compressed snapshot per hour is small; crawling 1,865 per-item requests each hour would be the wrong implementation. The browser's ordinary HTTP cache handles conditional requests and unchanged transfers. Cache/check time, snapshot publication time and each item's latest market report must remain distinct. Missing prices need the existing on-demand fallback; clean equipment, exact IDs, sample counts and per-item/set units still need validation. Snapshot fields mix `24h` and `last10` bases, so the reference window must stay visible.

Snapshots stay local and are excluded from source/release uploads. An installed Chrome, Edge or Chromium runs headlessly with a dedicated profile and an ephemeral loopback browser endpoint, reads the same list loaded by the ordinary page, then exits. No personal browser profile or desktop input is used. Refreshes coalesce; failures back off for 5, 15 and then 60 minutes while retaining the last-good generation. Missing browsers fall back to item lookups. No browser is downloaded or bundled. The full-cache refresh is enabled by default and can be disabled.

The implemented browser path downloaded and validated the live 1,865-row/1,277-price list in 1,686 ms in one launch sample; the browser exited afterward. Against the saved Classic World catalog, 1,269 prices passed exact ID/name/unit checks, including 175 cash items. This is one network sample, not a guarantee; it happens in the background while saved prices remain usable. Snapshot-backed visible items issue zero per-item API calls. Old publication/report times, thin samples and unknown units cannot earn deal colors.

A Linux resource sample of the complete browser subtree peaked at 436.8 MiB proportional set size (PSS), ran for 1.87 seconds to obtain the list, and exited afterward. Summed RSS was 1,365 MiB because shared browser mappings are counted repeatedly. This is temporary refresh overhead, not resident idle usage. The cache option can be disabled; no compatible browser is installed automatically.
