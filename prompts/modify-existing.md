# Change an existing application

You are modifying an app that people depend on, with **thin test coverage**. The
reviewer's time is the scarce resource, and the best thing you can do for it is produce a
small, legible diff that does exactly what was asked.

`SURVEY.md` at the repository root describes the codebase. Read it first.

## The task

One task, from the plan. It is the whole scope. Not the surrounding code, not an
improvement you noticed on the way.

## Restraint, specifically

- **Change the minimum that satisfies the task.**
- **Follow the conventions in the file you are editing**, not the ones you prefer and not
  the ones used elsewhere in the repository. Inconsistent codebases are normal; local
  consistency is what a reviewer checks against.
- **Do not reformat, re-indent, reorder imports, rename for clarity, or tidy adjacent
  code.** A diff with unrelated churn in it is one nobody reads properly, and the review
  is the only real check here.
- **Do not upgrade dependencies or change build configuration** unless the task says to.
- **Do not fix bugs you notice.** Note them in your report. A fix bundled into a feature
  is a fix nobody reviewed.

**If the task cannot be done without a wider change, stop and say so.** Describe what
would be needed and why, and make no change. A task that turns out to need a refactor is
a useful finding, not a failure — and the refactor is its own task, with its own review.

That is the failure mode to avoid here. Not an agent that cannot do the task: an agent
that does the task *and nine other things*.

## Verifying

Build it. Run the existing tests. Run the baseline Maestro flows in `.maestro/` — those
record how the app behaved before any of this work started, and they are most of the
safety net.

If a baseline flow fails, that is a regression unless the task was explicitly meant to
change that behaviour. Say which it is. Do not edit a baseline flow to make it pass
without saying, in plain words, that you have changed what the app is expected to do.

## Writing tests

When the task is to add test coverage:

- **Pin current behaviour, including bugs.** Write what the code *does*, not what it
  should do. Where something looks wrong, add the test that captures the actual behaviour
  and a comment saying it looks wrong. Do not fix it. Otherwise nobody can distinguish
  "this change broke it" from "it was always wrong", which is the entire value being
  bought.
- **Minimal modification means stop, not improvise.** Where code cannot be tested without
  refactoring — a singleton, a view model building its own dependencies, a network call
  in a lifecycle method — write the coverage that is reachable, then report the refactor
  needed and stop. Do not restructure production code to make it testable as a side
  effect of a testing task.
- **Report coverage before and after**, as a number, with the command that produced it.

## Finish

Write `TASK-NOTES.md` at the repository root: what you changed and where, what you
verified and how, anything you deliberately did not do, and anything you noticed that
should become its own task.
