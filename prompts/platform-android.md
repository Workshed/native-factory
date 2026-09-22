## This conversation: Android only

Build into `android/`. Kotlin and Jetpack Compose. Scaffold with
`android create --name="<app name>" --output=android empty-activity`, then build and
install with `./gradlew installDebug`.

An emulator is already connected and reachable through plain `adb` — do **not** try to
start one, it cannot run in this VM. Check `adb devices` to confirm.

Finish with the app built, installed and running, with Maestro flows in
`android/.maestro/` covering the main journey and at least one validation case. Always
pass `--device emulator-5554` to Maestro.

Write `android/NOTES.md`: what you built, which deviations you made deliberately and why,
and anything in the reference material you could not resolve.
