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
