# Releasing Pausio on GitHub

Pausio's early-access releases are **versioned Python distributions**, not signed macOS applications. Release assets are built and verified by GitHub Actions on an exact commit.

## First release: v0.1.0

The first release is defined in `.github/release/manifest.json` with the notes `.github/release/v0.1.0.md`. Once the PR containing the workflow and manifest merges to `main`, the `Publish GitHub Release` workflow runs automatically.

It will:
1. Verify `manifest.tag`, `pyproject.toml` and `pausio.__version__` match.
2. Execute project tests and validate FFmpeg/libass availability on Python 3.12.
3. Build a source distribution and wheel, validate package metadata, inspect bundled Studio assets and smoke-test wheel installation from outside the checkout.
4. Compute SHA-256 digests for both assets.
5. Create an annotated `v0.1.0` tag at the *tested* commit (never move an existing tag).
6. Publish a GitHub **pre-release** with wheel, sdist and `SHA256SUMS.txt`, using the checked-in release notes.

The workflow can be rerun manually from Actions on `main`; it refuses to move an existing version tag and leaves an already published release unchanged.

## Future releases

- Finish and review implementation + CI before the release commit.
- Update the version in `pyproject.toml` and `src/pausio/__init__.py`.
- Add a new `.github/release/vX.Y.Z.md` and change `.github/release/manifest.json` (tag, display name, prerelease flag).
- Merge a PR to `main` to publish. Verify the GitHub Releases page and asset hashes.
- Never modify existing tags/assets silently: publish another version to fix a broken release.

**Scope:** this workflow doesn't build a `.dmg`, create a notarized Mac app or publish to PyPI. The optional MLX transcription dependencies need Apple Silicon and real-device testing; no model weights are bundled.
