# ADR-0001 — Host CLI is Python 3.12+ managed by uv

Date: 2026-09-19 · Status: accepted (user decision, HANDOFF §2.1 — not to be reopened)

## Context

The brief asks for a brief comparison of Python and Go for the host CLI, specifically on macOS
distribution, subprocess management, YAML/JSON/SQLite, testing, packaging, and future
open-source contributions.

## Decision

Python 3.12+, managed by uv.

## Rationale

Go wins on exactly one axis that matters here: distribution as a single static binary with no
runtime. Python wins on the rest, and one factor is decisive: the **in-guest factory runtime must
be Python regardless**, because `openhands-sdk` is a Python library. Choosing Go for the host CLI
would mean two languages, two toolchains, two test setups and a serialization seam between host
and guest for no benefit, and would halve the pool of contributors able to work across the whole
system.

The remaining axes:

- **Subprocess management** — a wash. `os/exec` and `subprocess` are both adequate for driving
  `tart`, `packer`, `xcodebuild`, Gradle and `adb`.
- **YAML/JSON/SQLite** — a wash. Both have solid YAML libraries and first-class SQLite.
- **Testing** — a wash; pytest is if anything richer for the table-driven argv tests this CLI
  needs.
- **Packaging/distribution** — Go's advantage, materially narrowed by uv. `uv sync` gives
  contributors a reproducible environment in seconds; `uv tool install` covers end-user
  installation until Homebrew packaging arrives at Milestone 10.
- **Open-source contribution** — Python, because of the single-language argument above.

## Consequences

- One language across host CLI, guest runtime and shared schema code.
- Distribution before Milestone 10 is `uv tool install`, not a downloadable binary.
- The discovery crawler is the one exception (ADR-0003's sibling reasoning; see
  `docs/architecture.md` §14) — Node, confined to `crawler/` behind a JSON contract.
