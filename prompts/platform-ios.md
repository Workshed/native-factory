## This conversation: iOS only

Build into `ios/`. Swift and SwiftUI, `xcodebuild` and `xcrun simctl`. Hand-writing the
`.xcodeproj` is fine and has worked here before.

Finish with the app built, installed and running on a booted simulator, with Maestro
flows in `ios/.maestro/` covering the main journey and at least one validation case.
Always pass `--device <simulator-udid>` to Maestro.

Write `ios/NOTES.md`: what you built, which deviations you made deliberately and why, and
anything in the reference material you could not resolve.
