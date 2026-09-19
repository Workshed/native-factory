You are the implementing agent for Native Factory, a new open-source project in this empty directory.

Read these two files completely before doing anything else:
1. `Native Factory — Engineering Brief.md` — the original brief.
2. `HANDOFF.md` — a review of the brief against upstream documentation as of 2026-09-19. Where HANDOFF.md contradicts the brief, HANDOFF.md wins. Section 2 lists decisions already made; do not reopen them. Section 7 is verified research; do not repeat it. Section 8 lists unknowns to resolve empirically later, not now.

Your task is exactly HANDOFF.md section 9:
- Write `docs/architecture.md` and `docs/implementation-plan.md`.
- Propose the repository structure.
- Propose Milestone 1 in detail with runnable acceptance tests.
- Then STOP and present the plan for approval.

Constraints:
- Planning only. Do not `git init`, install anything, create the VM, or write code yet.
- Host CLI is Python 3.12+ with uv. The in-guest runtime is Python using the OpenHands SDK.
- Keep the OpenHands Agent Canvas + ACP boundary; no Claude-specific logic in the factory.
- The Android Emulator runs outside the macOS guest (HANDOFF.md 4.5). iOS and Android are both required.
- Include agent-device with the role split in HANDOFF.md 4.9.
- Cite the HANDOFF.md section you relied on wherever a design choice differs from the brief.

When you present the plan, lead with anything in HANDOFF.md you disagree with or found to be wrong, then the plan.
