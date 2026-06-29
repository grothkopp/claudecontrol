# Homebrew cask for the prebuilt ClaudeControl.app.
#
# To publish: build the app (./scripts/build-app.sh), zip it, attach the zip to
# a GitHub release, then fill in `sha256` below and host this file in a tap repo
# named `homebrew-claudecontrol` so users can:
#
#   brew tap grothkopp/claudecontrol
#   brew install --cask claudecontrol
#
# (The default `brew install claudecontrol` uses the Formula instead — see
# docs/packaging.md. Use whichever you prefer to publish.)
cask "claudecontrol" do
  version "0.1.0"
  sha256 :no_check # replace with the zip's sha256 once a release exists

  url "https://github.com/grothkopp/claudecontrol/releases/download/v#{version}/ClaudeControl-#{version}.zip"
  name "Claude Control"
  desc "Menubar app surfacing the Claude desktop app's tasks across Chat/Cowork/Code"
  homepage "https://github.com/grothkopp/claudecontrol"

  depends_on macos: ">= :sonoma"

  app "ClaudeControl.app"

  caveats <<~EOS
    claudecontrol reads the Claude desktop app through the macOS Accessibility
    API. Grant it access under:
      System Settings → Privacy & Security → Accessibility

    Unofficial tool — not affiliated with Anthropic.
  EOS
end
