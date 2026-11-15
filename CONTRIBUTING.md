# Contributing

Use Python 3.12.13 and uv. Run the setup and host commands in [README](README.md); do not install dependencies with pip or create a manual virtual environment.

1. Create a branch from main. Add a behavior or regression test and confirm the intended failure before changing implementation.
2. Make the smallest change that passes the test, then run the relevant regression tests. Record the Red/Green commands and results in the PR.
3. Update the English and [Japanese README](README.ja.md) together when setup, features, or limits change. Detailed engineering records may remain in Japanese.
4. Run repository checks, the publication boundary checker, and host tests. Push the branch and open a PR.
5. Merge after all four required CI checks pass and review conversations are resolved. Main protection applies to administrators too; do not bypass it.

See [CI/CD](docs/ci-cd.md) for required checks, dependency updates, and source releases. Approval by a second person is optional for solo development. CI success does not establish physical display, input, sound quality, or safe firmware restoration.

Keep stock firmware, recordings, credentials, device identifiers, binaries, and build caches out of commits. Device writes require a separate, concrete review and permission. `scripts/flash.sh` must continue to refuse. Preserve Apache-2.0 and third-party license notices.
