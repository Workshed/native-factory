# ADR-0002 — The Android Emulator runs outside the macOS guest

Date: 2026-09-19 · Status: accepted (HANDOFF §4.5), gate moved to Milestone 1

## Context

ARM64 Android system images require Hypervisor.framework. `-accel off` exists only for x86
images, and Google states that a VM-accelerated emulator cannot run inside another VM. Inside a
Tart macOS guest the emulator fails with `HV_UNSUPPORTED` (Tart issue #881, closed not-planned;
GitHub macOS runners and MacStadium document the same).

Both iOS and Android are required (HANDOFF §2.2), and Tart is the system's only isolation layer.

## Decision

Only the emulator leaves the guest. The Android SDK, Gradle builds, unit tests and
Robolectric stay in the guest. The emulator runs on the host, and **a forwarder on each
side** bridges it in — `scripts/adb-bridge.sh`.

```text
host   adb start-server                      127.0.0.1:5037
       socat  <gateway>:5037  ->  127.0.0.1:5037
       socat  <gateway>:5554  ->  127.0.0.1:5554     (emulator console)

guest  socat  127.0.0.1:5037  ->  <gateway>:5037
       socat  127.0.0.1:5554  ->  <gateway>:5554
```

**Verified end to end on 2026-09-22.** A Compose app created with `android create` inside
the guest built, installed onto the host emulator (`Installed on 1 device.`), launched,
and passed a Maestro flow with JUnit output — all four ADB clients working with **no
environment variables set**.

### Why forwarders rather than `ADB_SERVER_SOCKET`, and why not a firewall

Three measured facts, none of which were obvious from the documentation:

1. **adb cannot bind one interface.**

       $ adb -L tcp:192.168.64.1:5037 server nodaemon
       could not install *smartsocket* listener: listening on specified hostname
       currently unsupported

   HANDOFF 4.5's `adb -a` plus a root-loaded pf anchor would work, but a forwarder is
   better on three counts: adb is never exposed on all interfaces even briefly, no root
   is needed (5037 is unprivileged), and there is no firewall state to load, verify or
   forget to remove.

2. **AGP does not honour `ADB_SERVER_SOCKET`.** With it set correctly, Gradle
   `installDebug` hangs on `[DeviceMonitor]: Cannot reach ADB server, attempting to
   reconnect` — it installs its own platform-tools and looks for a local server. This is
   the question HANDOFF 8.2 asks only of Maestro; AGP fails it independently, as
   predicted.

3. **A guest-side forwarder makes the question moot.** Forwarding `127.0.0.1:5037` inside
   the guest makes every client's localhost assumption *true*. Nothing has to honour
   anything. That is why adb, Gradle and Maestro all pass with no environment set — and
   why a future client that also ignores the variable will work anyway.

Port 5554 is the emulator **console**, not adb: it carries the device name and the
console-only features (GPS, SMS, battery). It needs the host's
`~/.emulator_console_auth_token`, which `adb-bridge.sh up` copies in. Without it Maestro
still passes but reports
`device="error: could not connect to TCP port 5554: Connection refused"`.

Configuration: `targets.android.emulator: host | linux-vm | host-fallback`.

## Gate — passed

The spike moved from Milestone 6 to the start of the work, and **passed on 2026-09-22**.
`scripts/adb-bridge.sh verify` re-runs it. The fallback ladder below was not needed.

Historical note: the spike moved forward because It needs only a booted
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
