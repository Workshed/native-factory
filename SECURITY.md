# Security

Native Factory is pre-alpha and not yet published, so there is no disclosure address yet.

The security model — and in particular what the Tart VM does and does not protect you
from — is documented in [`docs/security.md`](docs/security.md). Read it before pointing
the factory at anything you care about. The short version:

**The VM is the only isolation boundary.** OpenHands auto-grants every ACP permission
request and launches the coding agent with permissions bypassed, and the inspected website
is untrusted input travelling in the same prompt as trusted instructions. Use a dedicated,
rotatable API key.
