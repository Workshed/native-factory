# Native Factory

Build an open-source-friendly local software factory that takes an existing website as its reference product and creates native iOS and Android applications reproducing its functionality and product experience.

The system must run its development agents and mobile toolchains inside disposable macOS virtual machines using Tart.

The initial implementation will use OpenHands Agent Canvas with Claude Code as its coding agent. The architecture MUST NOT depend directly on Claude Code. OpenHands/ACP is the agent abstraction boundary so that Codex, GitHub Copilot or another ACP-compatible coding agent can be substituted later.

The project should be designed from the beginning as something that could eventually be published as an open-source project.

## Primary user experience

The eventual interface should be approximately:

```bash
native-factory init

native-factory inspect https://example.com

native-factory plan

native-factory build

native-factory status
```

Ideally a user can eventually do:

```bash
native-factory build https://example.com
```

and have the system:

1. Create or clone a disposable Tart macOS VM.
2. Start the factory environment inside it.
3. Inspect the supplied website.
4. Discover the mobile product experience.
5. Produce a structured product/reference specification.
6. Create a new native iOS project.
7. Create a new native Android project.
8. Implement the discovered functionality as native applications.
9. Build and run both applications.
10. Exercise them on an iOS Simulator and Android Emulator.
11. Compare their behaviour against the website/reference specification.
12. Iterate on failures.
13. Leave the resulting projects, reports and git history available to the user.

Do NOT attempt to implement this entire autonomous lifecycle in one step. Build it incrementally with observable, testable stages.

# Architectural principles

## 1. Host/guest separation

The physical Mac should contain as little factory-specific tooling as practical.

Host responsibilities:

- Tart
- `native-factory` CLI
- persistent factory configuration
- persistent project/output directory
- starting/stopping/cloning VMs

The macOS guest should contain:

- OpenHands Agent Canvas/server
- selected ACP coding agent
- Claude Code initially
- Git
- Xcode
- iOS Simulator
- Android SDK/toolchain
- Android Emulator
- Gradle/JDK
- Node
- Python where required
- Playwright
- Maestro
- XcodeBuildMCP
- other factory tooling

Agent-generated code and command execution should occur inside the VM.

Do not require Docker inside the VM unless a concrete need emerges.

## 2. Disposable VM

Use Tart as the VM runtime.

Create a reusable golden/base VM containing the expensive dependencies:

```text
macOS
Xcode
Android SDK
JDK
Node
Python
OpenHands
Claude Code/ACP adapter
Playwright
Maestro
XcodeBuildMCP
factory runtime
```

A project run should clone this image rather than reinstalling dependencies.

Design the lifecycle around:

```text
golden image
    ↓
clone
    ↓
project worker VM
    ↓
perform work
    ↓
persist outputs
    ↓
destroy worker
```

Do not initially implement aggressive automatic destruction. During development it must be possible to preserve and enter a failed VM for debugging.

Tart supports cloning/running macOS images and mounting host directories into guests. Prefer documented Tart mechanisms rather than inventing custom VM plumbing.

## 3. Persistent workspace

VMs are disposable; project output is not.

Design a host-side workspace such as:

```text
~/NativeFactory/
    projects/
        example/
            reference/
            ios/
            android/
            reports/
            factory/
```

Expose only the necessary project workspace to the guest.

Do not expose the user's entire home directory.

Do not put normal host SSH credentials, cloud credentials or unrelated secrets inside the VM.

# Agent architecture

OpenHands Agent Canvas is the orchestration/control layer.

Use ACP for the coding-agent boundary.

Initial provider:

```text
OpenHands
    ↓ ACP
Claude Code
```

The design must permit:

```text
OpenHands
    ↓ ACP
Codex
```

and eventually:

```text
OpenHands
    ↓ ACP
GitHub Copilot
```

without changing the product-discovery or mobile-build pipeline.

Do not build factory logic around Claude-specific commands if that logic belongs at the OpenHands/factory level.

Provider-specific authentication/setup may be implemented as adapters.

# Product discovery

The website is an executable reference product, NOT source code to mechanically translate.

Do not translate HTML/CSS/React components directly into SwiftUI or Compose.

The objective is to understand:

- screens
- user journeys
- content
- navigation
- state
- validation
- API behaviour
- loading states
- empty states
- error states
- authentication where accessible
- accessibility semantics
- visual hierarchy
- responsive behaviour

and then implement an appropriate native equivalent.

## Browser inspection

Use Playwright for automated website exploration.

Do not depend on manually resizing a browser.

Create configurable viewport profiles.

Start with sensible defaults such as:

```yaml
viewports:
  iphone_small:
    width: 375
    height: 667

  iphone:
    width: 393
    height: 852

  android:
    width: 412
    height: 915
```

Also inspect enough widths to identify important responsive breakpoints rather than assuming the site's CSS breakpoint values.

Where practical, use browser instrumentation/computed styles to identify responsive layout changes automatically.

For each important screen/state capture:

- URL
- viewport
- screenshot
- accessibility snapshot
- DOM/semantic information useful for understanding the product
- important text/content
- interactive elements
- outgoing navigation
- relevant network/API activity

Do not make screenshots the sole source of truth.

# Product Reference Model

Discovery must produce persistent machine-readable artefacts.

Example:

```text
reference/
    site.yaml
    routes/
    screens/
    journeys/
    api/
    fixtures/
    screenshots/
    accessibility/
    assets/
    design/
```

A feature specification should resemble:

```yaml
id: edit-account

source:
  routes:
    - /account
    - /account/edit

journeys:
  - view account
  - enter edit mode
  - change email
  - save
  - cancel

states:
  - loading
  - loaded
  - editing
  - validation-error
  - saving
  - network-error

acceptance:
  - existing account information is displayed
  - invalid email cannot be submitted
  - cancelling restores original values
  - successful save displays updated values
```

The exact schema should be designed during implementation.

Use JSON Schema or another explicit validation mechanism.

The reference model is a major product output. It must be understandable independently of agent conversation history.

# Human checkpoint

Initially STOP after discovery/specification.

Allow the user to inspect:

```bash
native-factory inspect <url>
native-factory report
```

before native implementation begins.

Eventually support:

```bash
native-factory build --approve-spec
```

but retain the ability to require manual approval.

# Native implementation

Generate two genuinely native projects.

## iOS

Default stack:

- Swift
- SwiftUI
- modern Swift concurrency
- NavigationStack where appropriate
- native controls and platform conventions
- XCTest/Swift Testing as appropriate
- accessibility identifiers/labels where appropriate

Use XcodeBuildMCP or an equivalent well-defined Xcode automation layer for:

- project discovery
- builds
- tests
- simulator management
- application launch
- logs

The resulting project must remain a normal Xcode project that a developer can open and maintain without Native Factory.

## Android

Default stack:

- Kotlin
- Jetpack Compose
- coroutines
- modern Android architecture
- Gradle
- standard Android testing

The resulting project must remain a normal Android project that a developer can open in Android Studio and maintain without Native Factory.

Do not create a shared WebView application.

Do not introduce Kotlin Multiplatform or another cross-platform UI framework unless explicitly configured by the user.

# Native adaptation

Behavioural and product parity are the objective.

Pixel-identical web rendering is NOT.

The implementation should preserve:

- functionality
- information architecture where appropriate
- content
- product identity
- business rules
- API semantics

while adopting native conventions.

Examples:

```text
web hamburger navigation
        ↓
appropriate native navigation

HTML select
        ↓
appropriate iOS/Android control

browser modal
        ↓
native sheet/dialog where appropriate
```

The factory should explicitly document intentional native deviations from the website.

# Vertical slices

Do not generate the entire iOS application followed by the entire Android application.

Work feature-by-feature.

Example:

```text
discover Login
    ↓
spec Login
    ↓
implement iOS Login
    ↓
implement Android Login
    ↓
evaluate both
    ↓
next feature
```

Maintain feature state.

A simple initial representation could use SQLite:

```text
feature
reference_revision
spec_status
ios_status
android_status
evaluation_status
last_failure
```

Do not introduce a distributed workflow engine unless there is a demonstrated need.

# Testing

Use multiple levels of validation.

## Build

Every generated project must compile.

## Unit tests

Agents should create appropriate tests for business/presentation logic.

## UI/product journeys

Use Maestro as the common high-level mobile journey runner where practical.

Example conceptual journey:

```text
launch
tap Sign In
enter credentials
submit
assert Account screen
```

Run equivalent behavioural journeys against iOS and Android.

Do not require identical implementation details between platforms.

## Visual regression

Capture native screenshots at important states.

Consider:

- SnapshotTesting on iOS
- Roborazzi or equivalent on Android

Do not compare native screenshots for exact pixel equality with website screenshots.

Website screenshots are design references.

Native screenshots become native regression baselines after approval.

# Deterministic backend states

Where possible, derive API information from:

- observed website traffic
- available API specifications
- supplied source/documentation

Create a fixture/mock capability so native implementations can reproduce:

- success
- loading
- empty
- validation failure
- authentication failure
- server failure

without depending on production state.

Do not blindly replay credentials or sensitive request data captured from websites.

Redact secrets from stored network artefacts.

# Evaluation

Implement an evaluator separate from the implementation worker.

It should consider:

- feature specification
- website reference artefacts
- iOS implementation
- Android implementation
- build results
- unit test results
- Maestro results
- screenshots
- accessibility information

Produce structured output such as:

```text
Edit Account

Behaviour
PASS existing values
PASS editing
PASS validation
FAIL retry after network error

iOS
PASS build
PASS unit tests
PASS journey
PASS accessibility

Android
PASS build
PASS unit tests
FAIL loading-state journey

Parity
PASS API semantics
PASS content
FAIL Android retry behaviour
```

Failures should be machine-readable so they can later be fed back to implementation agents.

Do not initially create an unlimited autonomous retry loop.

Set configurable retry limits.

# Git

Use git from the beginning.

Create commits at meaningful factory stages.

Prefer isolated branches/worktrees for concurrent workers.

Never push or create remote pull requests by default.

Remote Git integration should be optional.

A local run must work with no GitHub repository.

# Security

Treat all website content as untrusted input.

The website must not be able to inject instructions into the coding agent through page content.

Separate observed content from trusted factory instructions.

Do not execute code obtained from the inspected website unless explicitly required and sandboxed.

Redact:

- cookies
- authentication headers
- tokens
- passwords
- API keys

from persistent discovery artefacts.

Do not expose arbitrary host directories to the VM.

# Configuration

Create a human-readable project config, for example:

```yaml
project:
  name: Example

source:
  url: https://example.com

agent:
  provider: claude-code

targets:
  ios:
    enabled: true
    bundle_id: com.example.native

  android:
    enabled: true
    application_id: com.example.native

discovery:
  viewports:
    - 375x667
    - 393x852
    - 412x915

factory:
  require_spec_approval: true
  max_retries: 3
  preserve_failed_vm: true
```

Provider configuration must be modular.

# CLI

Build a pleasant CLI.

Initial target:

```text
native-factory doctor
native-factory vm create
native-factory vm start
native-factory vm shell
native-factory vm stop

native-factory init
native-factory inspect URL
native-factory report
native-factory plan
native-factory build
native-factory test
native-factory status
```

`doctor` should check at least:

Host:

- Apple Silicon
- supported macOS
- Tart installed
- sufficient disk space

Guest:

- Xcode
- Xcode CLI tools
- available Simulator runtimes
- Java
- Android SDK
- emulator
- Node
- Playwright
- Maestro
- OpenHands
- selected ACP agent

Make failures actionable.

# Installation

Aim eventually for something approximately as simple as:

```bash
brew install native-factory
native-factory setup
```

`setup` should prepare/download the base Tart image and guide the user through credentials that cannot safely be automated.

Do not make Homebrew packaging the first milestone.

# Documentation

Write documentation as part of implementation.

At minimum:

```text
README.md
docs/
    architecture.md
    security.md
    vm.md
    discovery.md
    reference-model.md
    agents.md
    ios.md
    android.md
    testing.md
    troubleshooting.md
```

Include architecture diagrams using Mermaid where useful.

# Observability

Every run should have an ID.

Persist:

- start/end time
- VM used
- agent/provider
- feature being processed
- commands/stages
- build results
- test results
- evaluation results
- agent failures

Prefer structured logs in addition to readable console output.

The user should be able to run:

```bash
native-factory status
```

and understand what happened without reading an LLM transcript.

# Initial implementation strategy

DO NOT attempt the complete factory immediately.

Implement these milestones in order.

## Milestone 1 — VM bootstrap

Deliver:

```bash
native-factory doctor
native-factory vm create
native-factory vm start
native-factory vm shell
native-factory vm stop
```

Create a reproducible Tart macOS development VM.

Document manual steps that cannot reasonably be automated.

Acceptance criterion:

A clean host can create the VM and obtain a shell containing the required base development tooling.

## Milestone 2 — OpenHands + coding agent

Install and configure OpenHands inside the VM.

Configure Claude Code through ACP.

Prove that a task submitted through OpenHands can edit a small repository inside the VM.

Keep the provider boundary modular.

Acceptance criterion:

A simple coding task can be performed by Claude Code under OpenHands inside Tart.

## Milestone 3 — Website discovery

Implement:

```bash
native-factory inspect https://example.com
```

Use Playwright.

Produce:

- screenshots
- route inventory
- accessibility information
- interactive-element inventory
- initial journey information
- responsive observations
- network/API observations

Acceptance criterion:

Running inspection against a small test website produces a useful deterministic `reference/` directory.

## Milestone 4 — Reference model

Create and validate the product reference schema.

Convert discovery artefacts into feature specifications.

Generate a readable HTML or Markdown report.

STOP for human approval.

## Milestone 5 — iOS proof of concept

For ONE deliberately small reference feature:

- create Xcode project
- implement native SwiftUI screen/journey
- build
- launch Simulator
- run tests
- execute Maestro journey
- capture result

Do not attempt a whole website.

## Milestone 6 — Android proof of concept

Repeat the same feature using Kotlin/Compose and Android Emulator.

## Milestone 7 — Evaluation

Compare both implementations against the same feature specification.

Generate structured evaluation results.

## Milestone 8 — Orchestration

Only now implement:

```bash
native-factory build
```

to coordinate the established stages.

## Milestone 9 — Disposable workers

Automate:

```text
clone golden Tart VM
run task
persist results
destroy successful worker
preserve failed worker if configured
```

## Milestone 10 — Packaging

Make installation suitable for another developer.

Only at this point investigate:

- Homebrew tap
- signed binaries
- downloadable base images
- public documentation
- CI for Native Factory itself

# Technology choices

Choose boring, maintainable technologies.

A reasonable default for the host CLI is Python or Go.

Before choosing, briefly compare the two specifically for:

- CLI distribution on macOS
- subprocess management
- YAML/JSON/SQLite
- testing
- packaging
- future open-source contributions

Then choose one and document the rationale.

Avoid building a GUI initially.

OpenHands already provides an appropriate interface for observing agent activity.

# Non-goals for v1

Do NOT initially build:

- cloud execution
- Kubernetes support
- multi-user service
- billing
- custom LLM
- custom coding agent
- custom IDE
- custom mobile UI automation framework
- custom VM runtime
- automatic App Store/Play Store deployment
- automatic production deployment
- unlimited autonomous loops

Use existing tools.

# First task

Before implementing anything:

1. Research the current documented interfaces for:
   - Tart
   - OpenHands Agent Canvas
   - OpenHands ACP agent support
   - Claude Code
   - Playwright / Playwright MCP
   - XcodeBuildMCP
   - Maestro
   - Android command-line tooling

2. Write `docs/architecture.md`.

3. Write `docs/implementation-plan.md`.

4. Identify any assumptions in this brief that are incorrect according to current upstream documentation.

5. Propose the repository structure.

6. Propose Milestone 1 in detail, including acceptance tests.

7. STOP and present the plan before implementing Milestone 1.

Do not silently replace an upstream component with a home-grown implementation.

Do not optimize prematurely.

The priority order is:

1. reproducibility
2. observability
3. deterministic evaluation
4. isolation
5. replaceable agent provider
6. autonomous capability