# Lupin updates

Packaged builds check GitHub on launch and every six hours while open or in the
tray. Settings provides a launch toggle, a 15-minute to seven-day interval,
periodic checks off, and Check now. Checks share a one-minute cooldown and obey
GitHub rate-limit backoff. Source checkouts can check manually but do not install.

An available release adds a Settings badge and tray action without moving the
Prices layout. The desktop notification opens a compact update sheet. Download &
install authorizes downloading, verification, installation and restart. Later
leaves the badge; the same version is not announced on every check. Cancelling a
download or system authentication leaves the current application running.

The updater reads the public `zhuffman68/lupin` GitHub release feed without a token
or browser. Only published stable releases and newer numeric versions qualify.
It requires a public repository and correctly signed release; implementation
does not publish releases or change repository visibility.

## Verification and transfer size

`lupin-update.json` names exact platform/version artifacts, byte counts and SHA-256
hashes. `lupin-update.sig.json` is an Ed25519 signature over canonical UTF-8 JSON.
Only keys pinned in `price_lens/resources/update-keys.json` are accepted. OpenSSL
performs verification without another Python crypto package. Windows downloads
use the same native certificate-chain context as market data.

Metadata, redirects, request sizes, download sizes, deadlines and worker counts
are bounded. Requests cannot leave HTTPS GitHub asset hosts. A failed download
does not replace a good package. Unknown keys, duplicate JSON keys, wrong
repositories/platforms, older versions and checksum mismatches fail closed.

Optional patches reconstruct the exact new installer/package in the user cache.
They never patch managed installation files. Each zstd prefix dictionary is at
most 8 MiB and decoder windows are capped at 32 MiB, avoiding a whole installer
in memory. The result must match the signed full-package hash. Wrong bases,
damaged patches and unsupported decoding fall back to the full download.
Release preparation omits patches at or above 80 percent of the full size;
compression changes can make a full download preferable.

Two verified bases are retained through hard links, without extra model copies
for each cache filename. The first update normally needs a full download because
an existing installation does not contain its own installer. Both translation
models remain included and unchanged.

## Native installation

- **Windows:** the existing per-user Inno installer runs with
  `/VERYSILENT /NORESTART /SP-`. The external PowerShell helper runs from the user
  cache, checks the hash again, and outlives the app's runtime.
- **Manjaro/Arch:** a fixed root-owned helper uses graphical polkit authentication
  and `pacman -U` on the verified native package.
- **Debian/Ubuntu:** the same helper authenticates and passes the verified DEB to
  `apt-get install`. Package ownership/dependencies remain system-managed.

Portable Windows releases are retired. Close an older portable copy and install
the current Windows installer manually before using in-app updates.

The Linux helper accepts no arbitrary command. It checks the installed root,
platform and newer version, independently re-verifies the pinned signature, and
copies/hashes the payload into a root-owned cache before acknowledging readiness.
Native package metadata must also name Lupin with the exact version and architecture.
Authentication is not retained. Only an explicit commit followed by EOF from the
GUI's own pipe starts installation, after tracking has been saved and the app
closed. The helper relaunches Lupin as the invoking user with a short allowlist
of desktop environment variables. Failed transactions keep a small system log.

Compatible app-only releases may list an older version in the signed
`capture_compatible_from` field. Only then can a live reader hand off its sharing
helper on Linux and reconnect after restart. Windows closes its helper so runtime
DLLs can be replaced, then reconnects if the signed compatibility rule permits.
By default capture closes and the user
starts it again. Tracking always starts stopped after restart; preferences,
watchlist, database and caches remain in their usual user directories.

## Preparing a release

This prepares local assets after normal builds/tests; it never uploads them.
The owner must retain and back up the private signing key outside the repository.
Only its public key belongs in source or packages.

```sh
python scripts/release_updates.py keygen --key /path/outside/repository/update-key.pem
python scripts/release_updates.py prepare --key /path/outside/repository/update-key.pem
```

The second command requires the three current packages in `dist/`: the Windows
installer, Arch/Manjaro package and Debian/Ubuntu package. It then creates the two
signed metadata assets. Optional `--base-manifest /previous/lupin-update.json
--base-dir /previous/artifacts` generates useful deltas; all bases must match that
manifest. Add `--capture-compatible-from X.Y.Z` only after verifying compatible
capture/runtime/protocol files. Upload metadata, useful patches and full artifacts
to their matching `vX.Y.Z` GitHub release when publication is authorized.

## Acceptance boundaries

Tests cover real OpenSSL known-answer signatures, tampering, fake GitHub ETags,
verified local downloads, chunked patches, cancellation, timer settings and the
install-commit protocol. Wine/offscreen checks do not prove native Windows
authentication, PowerShell installation or game capture. Real installer
transactions and live public-feed acceptance require the eventual release
packages; source implementation alone does not establish those claims.

## Historical patch experiment

A 0.17.5 → 0.17.6 archive experiment reconstructed all four files with
matching SHA-256 hashes, using about 81–96 MiB peak process memory. The portable
Windows ZIP shrank from 425.4 MB to a 22.7 MB patch. The solid Windows installer,
Arch package and DEB patches remained 98–100 percent of their full sizes, so the
80-percent rule rejects those patches. Their normal update path currently uses
full native downloads. Splitting stable runtime/models into separately versioned
components would be a separate packaging change, not an established benefit of
these native-package deltas. The ZIP measurement concerns the retired portable
format. No release artifacts were rebuilt by this experiment.
