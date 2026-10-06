# Survey an existing application

**Change nothing in this conversation.** The output is a document.

A repository is mounted at the working directory. Read it and write `SURVEY.md` at its
root describing what is actually there — not what good practice would suggest, and not
what the README claims.

This is the document a human reads at the gate before any code is touched, and the one
every later task is planned against. Its value is accuracy, not completeness: a short
survey that is right beats a long one that is partly inferred.

## What to cover

**Layout** — modules or packages, and what each is for. Where the app starts.

**Navigation** — how screens are reached and how that is wired. Name the mechanism
(storyboards, `NavigationStack`, Navigation Compose, a custom coordinator) and say where
the graph is defined.

**State and data** — how view state is held, how data reaches the UI, where networking
and persistence live.

**Tests** — frameworks, where tests live, roughly what is covered and, more usefully,
**what is not**. Say whether the suite currently passes and how long it takes. If you
cannot run it, say so rather than guessing.

**Build** — targets, flavours, schemes, build configuration, anything needed to produce a
debug build. Record the exact commands that worked.

**Conventions actually in use** — naming, file organisation, formatting, patterns. Note
where the codebase is inconsistent, because that tells a later task which local style to
follow.

**Risk areas** — the parts that would be hard to change safely: singletons, globals,
view models constructing their own dependencies, networking in lifecycle methods, very
large files, anything untestable without refactoring. This section is the most useful
thing in the document; be specific and name files.

## How to work

Read widely before writing. Run the build and the tests if you can — a survey that says
"the suite passes in 40 seconds" is worth more than one that lists test file names.

Where you are inferring rather than observing, say so. "Probably MVVM, though
`AccountViewController` holds its own networking" is useful. "Uses MVVM" is not, if it is
only true in half the codebase.

Do not propose changes, plan work, or offer opinions on architecture. The next stage does
that, against a plan a human has approved.

## Finish

Report: the shape of the app in a few sentences, whether you could build and test it, and
the three things most likely to make changes risky.
