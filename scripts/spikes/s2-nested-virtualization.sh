#!/usr/bin/env bash
#
# Spike S2 -- Linux nested virtualization on this host (HANDOFF 8.1, plan AT-8).
#
# Informational. It gates nothing today; it decides whether
# targets.android.emulator: linux-vm becomes viable later, since Linux guests are not
# subject to the two-macOS-guest ceiling.
#
# Tart's docs claim M3/M4. M5 is unverified, which is the whole reason for this script.

set -uo pipefail

VM="${1:-nf-nested-probe}"
IMAGE="ghcr.io/cirruslabs/ubuntu:latest"

cleanup() {
  tart stop "$VM" >/dev/null 2>&1 || true
  tart delete "$VM" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== macOS guests must be rejected for --nested =="
# Tart throws for any macOS guest with --nested. Asserting this keeps someone from
# "fixing" the emulator problem by nesting a macOS VM.
if tart run --nested --no-graphics nf-golden >/dev/null 2>&1; then
  echo "UNEXPECTED: tart accepted --nested for a macOS guest" >&2
  tart stop nf-golden >/dev/null 2>&1 || true
else
  echo "  ok: tart rejects --nested for macOS guests, as documented"
fi

echo
echo "== Linux guest with --nested =="
tart clone "$IMAGE" "$VM" || { echo "could not clone $IMAGE" >&2; exit 1; }
tart run --nested --no-graphics "$VM" >/dev/null 2>&1 &
sleep 45

if ! tart ip "$VM" >/dev/null 2>&1; then
  echo "  FAIL: guest did not boot with --nested" >&2
  exit 1
fi

result="$(tart exec "$VM" sh -c 'ls -l /dev/kvm 2>&1; echo "---"; grep -c . /proc/cpuinfo' 2>&1)"
echo "$result"

if echo "$result" | grep -q '/dev/kvm'; then
  echo
  echo "  PASS: /dev/kvm is present -- nested virtualisation works on this host."
  echo "  emulator: linux-vm is worth revisiting (see docs/architecture.md section 6)."
  verdict=0
else
  echo
  echo "  FAIL: no /dev/kvm -- nested virtualisation is unavailable."
  echo "  emulator: host remains the only option. Record this in docs/vm.md."
  verdict=1
fi

exit $verdict
