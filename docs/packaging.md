# Packaging & distribution

Two ways to ship `claudecontrol`. A **formula** is simplest (no prebuilt binary;
runs the scripts via `uv`). A **cask** ships a real double-clickable `.app`.

Both live in a Homebrew **tap** — a repo named `homebrew-<tap>`. For
`brew tap grothkopp/claudecontrol`, that's `grothkopp/homebrew-claudecontrol`.

---

## Option A — Formula (recommended, no build needed)

`brew install` installs the three source files + a `claudecontrol` launcher that
starts the menubar app via `uv`. The source tarball is the one GitHub generates
automatically for a tagged release, so there's nothing to build or upload.

`Formula/claudecontrol.rb` in the tap repo:

```ruby
class Claudecontrol < Formula
  desc "Menubar app surfacing the Claude desktop app's tasks across Chat/Cowork/Code"
  homepage "https://github.com/grothkopp/claudecontrol"
  url "https://github.com/grothkopp/claudecontrol/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "MIT"

  depends_on "uv"
  depends_on :macos

  def install
    libexec.install "claudebar.py", "claude-state.js", "claude-focus.js"
    (bin/"claudecontrol").write <<~SH
      #!/bin/bash
      exec uv run --quiet "#{libexec}/claudebar.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Start the menubar app:   claudecontrol
      Grant Accessibility access: System Settings → Privacy & Security → Accessibility
      Unofficial — not affiliated with Anthropic.
    EOS
  end

  test do
    assert_path_exists libexec/"claudebar.py"
  end
end
```

Publish:

```sh
# 1) tag + release the source (auto-generates the tarball)
git tag v0.1.0 && git push origin v0.1.0
gh release create v0.1.0 --title v0.1.0 --notes "First release"

# 2) get the tarball sha256
curl -sL https://github.com/grothkopp/claudecontrol/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256

# 3) create the tap repo and add the formula
gh repo create grothkopp/homebrew-claudecontrol --public
#   ...add Formula/claudecontrol.rb with the sha256 from step 2, commit, push

# users then:
brew tap grothkopp/claudecontrol
brew install claudecontrol
```

---

## Option B — Cask (double-clickable .app)

Ship the self-contained `ClaudeControl.app` (built with py2app).

```sh
./scripts/build-app.sh                                  # → dist/ClaudeControl.app
(cd dist && zip -r -y ClaudeControl-0.1.0.zip ClaudeControl.app)
gh release create v0.1.0 dist/ClaudeControl-0.1.0.zip   # attach the zip
shasum -a 256 dist/ClaudeControl-0.1.0.zip              # → sha256 for the cask
```

Put [`Casks/claudecontrol.rb`](../Casks/claudecontrol.rb) (with the real
`sha256`) in the tap repo, then:

```sh
brew tap grothkopp/claudecontrol
brew install --cask claudecontrol
```

> A py2app bundle is unsigned by default; users may need to right-click → Open
> the first time (or you can codesign/notarize it). The formula route sidesteps
> this since it runs the scripts directly.

---

## Notes

- The app needs **Accessibility** permission regardless of install method.
- `setup.py` sets `LSUIElement` so the `.app` is menubar-only (no dock icon).
- Renaming the project later: `gh repo rename`, and update the tap/formula token.
