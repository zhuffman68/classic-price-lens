# Lupin 0.17.3

- EXP validation can recover from an incorrect earlier inferred total. Three fresh changing EXP values and compatible percentages are required; unchanged or duplicate-time readings cannot replace it. Recovery keeps the session and confirmed gain, excluding the untrusted interval.
- The tracker distinguishes a hidden/unreadable bar from inconsistent numbers or an unreadable character name. Warmup explicitly asks for 30 seconds of clear EXP readings. Session gain can appear before rates; a positive pace is required for ETA.
- Larger rolling gain totals span the rate area, beside two smaller rate lines. Bold EXP/MESO labels, aligned percent/coin units, timers and Level X - ETA remain. The stack is 114 pixels tall and stays beside the HUD without painting over its identification guards.
- Last 5 min identifies the rolling rate window. Shorter windows show their actual duration; session time has its own timer.

The complete 486-test source suite passes with three platform/offscreen skips. The 45 focused tracking checks cover baseline recovery, retained gains, poisoned initial values with occasional compatible reads, repeated figures/timestamps, pause/capture boundaries, clear-reading warmup, rolling-window labels, two-second cadence and large values without layout overlap. Painted overlays retain game-area detection across four window/UI scales.

A fresh start against the currently open Linux game accepted every observed EXP reading and established a pace after about 31 clear seconds. The original minute-or-two outage was already over and was not captured; it is not claimed reproduced. No game input was sent. Positive-gain/ETA and rare recovery behavior are covered by replay/model tests, distinct from the stationary live check. The previous session was saved to history and the approved sharing helper retained.

Builds and package checks are recorded in VERIFICATION.md and the completed verification file beside the artifacts. Uploads remain on hold. Permanent host installation is a separate step:

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.3-1-x86_64.pkg.tar.zst
```

Windows: run Lupin-0.17.3-Windows-x64-Setup.exe. Debian/Ubuntu: install lupin_0.17.3-1_amd64.deb with apt.

All 486 installed tests pass under Windows/Wine, pacman, Debian 12 and Ubuntu 22.04, with platform/headless skips. Installation/removal, upgrade where supported, file checks and retained user caches pass. Physical Windows gameplay remains a separate untested case for this patch.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.3-Windows-x64-Setup.exe | 408,838,802 | `9ea6b343f13ddd1a46208190b73d2eeab30d5eef5880ddd1f1a93d0cbf46236b` |
| Lupin-Windows-x64.zip | 425,289,585 | `0fbf4573de66559e8521e6d6c82f71901810dd5aa14dd9bcfa0c534ace48bf1a` |
| lupin-0.17.3-1-x86_64.pkg.tar.zst | 463,586,650 | `7cfc5d082f25ce7e795352762e2a4ddb7eb104b3394d52111b9a1234bdc15b1b` |
| lupin_0.17.3-1_amd64.deb | 431,434,732 | `0a91afabda7b926e1e6db3645ac75c533608f446dd0498f49410819e582c57fd` |
