# ADR-0007 — Prototype first: drop the factory infrastructure for v1

Date: 2026-09-20 · Status: accepted · **Supersedes much of ADR-0001, 0003, 0004, 0005**

## Context

Milestone 1 of the full plan was built in a day: a uv workspace with three Python
packages, a typed Tart wrapper, a Packer golden image, SQLite run records, stage-scoped
mounts, a host and guest doctor, and 277 tests. All of it green.

None of it demonstrated that an AI coding agent can build a working SwiftUI application.
Under the milestone plan, that question is first answered at **Milestone 5**.

A reviewer proposed a prototype-shaped alternative: manual VM, no CLI, no golden image,
no database, no schemas, no evaluator — get one website → iOS + Android workflow working
and add infrastructure only when a demonstrated problem requires it.

## Decision

Adopt the prototype shape, with three amendments.

The deciding argument is risk ordering. The riskiest unknowns are (a) whether an ACP
agent can iteratively build a working native application, and (b) whether the Android
emulator plumbing works at all. The milestone plan reaches (a) at Milestone 5. The
prototype reaches it at step 2. Everything built so far is infrastructure around a
capability nobody has yet demonstrated.

A second, unanticipated benefit: a persistent, manually configured VM **dissolves the
credential-injection problem**. With a disposable VM, every run must inject a credential
that the agent can then read from its own environment — the concern behind ADR-0006 and
the reason a broker proxy was being considered. With a persistent VM you log in
interactively once and the token lives in that VM's own config. Disposability created
that problem; dropping it removes it.

### Amendment 1 — the Android emulator still cannot live in the guest

The proposal placed the Android Emulator inside the VM. It cannot work: an ARM64 AVD
needs Hypervisor.framework and fails with `HV_UNSUPPORTED` when nested. This is physics,
not preference, and it would have stopped the proposal at its own First Task item 11.
**ADR-0002 survives unchanged**, along with `scripts/spikes/s1-android-adb-over-nat.sh`.

### Amendment 2 — `setup-guest.sh` instead of manual configuration

Not a Packer golden image, but not clicking through a README either. A hand-configured
VM you cannot recreate makes every later failure unattributable: your code, or your
machine? A shell script run against a fresh clone costs about what writing the README
steps costs, and `tart clone` serves as the snapshot.

### Amendment 3 — keep `doctor` and `docs/security.md`

`doctor` is now a single stdlib-only file with no package and no CLI framework. It earned
its place on day one by turning an opaque Homebrew failure into a twenty-second
diagnosis. `docs/security.md` is a page that already exists and is worth keeping before
the factory is pointed at a website anyone cares about.

## What this reverses

| Superseded | Because |
|---|---|
| ADR-0001 (Python CLI with uv) | There is no CLI. `doctor` is one stdlib script. |
| ADR-0003 (provider adapter layer) | ACP *is* the abstraction; OpenHands already selects providers. Building adapters on top duplicated it. About forty lines of credential-precedence logic were worth keeping; a four-class hierarchy was not. |
| ADR-0004 (factory owns recorded execution) | There is no evaluator to feed. Revisit when one exists. |
| ADR-0005 (stage-scoped read-only mounts) | There are no stages. The underlying concern — that the agent can rewrite the criteria it is judged against — returns with the evaluator. |

ADR-0002 (emulator placement) and ADR-0006 (egress deferred) stand.

## Consequences

- Roughly 3,300 lines of Python are removed. That is one day's work, and sunk cost is not
  an argument for keeping any of it. The prior state is preserved on the
  `archive/full-factory-m1` branch, not deleted, because the Tart wrapper and run records
  are plausible again at v2.
- The docs survive almost entirely. The knowledge was the durable asset, not the code.
- Two real defects found while building the discarded version survive as tests-in-prose
  inside `scripts/doctor.py`: the legacy `android` script that exits 0, and a version
  regex that read `v24.5.0` as `5.0`.
- "Reproducibility first" from the brief's priority order is explicitly downgraded for
  v1, in favour of "does this work at all". It returns at v2.
