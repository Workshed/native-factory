## This conversation: Android only

Build into `android/`. Kotlin and Jetpack Compose. Scaffold with
`android create --name="<app name>" --output=android empty-activity`, then build and
install with `./gradlew installDebug`.

An emulator is already connected and reachable through plain `adb` — do **not** try to
start one, it cannot run in this VM. Check `adb devices` to confirm.

Finish with the app built, installed and running, with Maestro flows in
`android/.maestro/` covering the main journey and at least one validation case. Always
pass `--device emulator-5554` to Maestro.

Also write `android/.maestro/capture.yaml`: a flow that walks the app's main screens
taking `takeScreenshot` at each, named so the order is obvious (`01-list`, `02-detail`…).
It is how the pipeline produces screenshots of the finished app, and it lives with the
app so it stays correct as navigation changes.

**It must not fail.** Maestro writes no screenshots at all when a flow fails — not even
the ones already taken — so a capture flow should navigate and screenshot and do nothing
else. No assertions beyond what is needed to wait for a screen, and no interactions that
might not be available: typing into a field, tapping a placeholder, exercising a feature.
Those belong in the test flows, where failing is the point.

Write `android/NOTES.md`: what you built, which deviations you made deliberately and why,
and anything in the reference material you could not resolve.
