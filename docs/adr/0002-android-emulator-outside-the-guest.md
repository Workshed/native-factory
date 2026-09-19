# ADR-0002 — The Android Emulator runs outside the macOS guest

Date: 2026-09-19 · Status: accepted (HANDOFF §4.5), gate moved to Milestone 1

## Context

ARM64 Android system images require Hypervisor.framework. `-accel off` exists only for x86
images, and Google states that a VM-accelerated emulator cannot run inside another VM. Inside a
Tart macOS guest the emulator fails with `HV_UNSUPPORTED` (Tart issue #881, closed not-planned;
GitHub macOS runners and MacStadium document the same).

Both iOS and Android are required (HANDOFF §2.2), and Tart is the system's only isolation layer.

## Decision

Only the emulator leaves the guest. The Android SDK, Gradle builds, unit tests and Roborazzi
(JVM) stay in the guest. For v1 the emulator runs on the host with a NAT-scoped adb server, and
guest-side clients reach it via `ADB_SERVER_SOCKET`.

Configuration: `targets.android.emulator: host | linux-vm | host-fallback`.

Three additions beyond HANDOFF §4.5:

1. **Firewalling, not binding.** `adb -a` binds `0.0.0.0`; adb cannot bind one interface.
   Scoping port 5037 to `192.168.64.0/24` requires a root-loaded pf anchor.
2. **Gateway discovery.** The guest derives the gateway from its default route. Tart's vmnet
   subnet is not guaranteed to be `192.168.64.1`.
3. **Device leases.** Two concurrent guests share one adb server and one emulator pool with no
   arbitration in HANDOFF's design. One AVD per worker, serial pinned via `ANDROID_SERIAL`,
   leases in `state.db`.

## Gate

The spike moves from the start of Milestone 6 to the end of Milestone 1. It needs only a booted
guest, the host emulator and a prebuilt APK, all of which exist at M1, and this host already has
the SDK and four AVDs. Deferring it would place M2–M5 on an unverified assumption whose failure
reopens the emulator placement, the config schema and the M9 concurrency model.

It tests three independent ADB clients — adb CLI, AGP/adblib, Maestro's dadb, and agent-device —
not just the one HANDOFF §8 item 2 names.

## Fallback ladder

HANDOFF §4.5's "fallback 2 = drop Tart entirely" is rejected as rung 2: Tart is the only
isolation layer and the source of reproducibility for *all* work, and discarding it for an
Android-only problem trades the whole security model for one platform's E2E tests.

1. Android build + emulator on host, agent stays in the guest via the mounted `android/` dir.
2. Android E2E degrades to JVM level — Robolectric + Roborazzi; emulator journeys unsupported.
3. Physical Android device on the host over USB.
4. Drop Tart — genuine last resort.

## Consequences

- The host gains two tools it would not otherwise need: `emulator` and `platform-tools` (≥ 35).
- Android on-device testing depends on host state, weakening its reproducibility relative to iOS.
- Milestone 9's scheduler must hold device leases as well as VM slots.
