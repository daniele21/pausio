# Contributing

Pausio is in early development. Before submitting contributions, please open a discussion/issue to agree on scope and licensing. The repository license has not yet been selected.

## Local checks

    python -m pip install -e .
    python -m unittest discover -s tests -v
    python -m compileall -q src

Use feature branches and small pull requests. Include unit tests for timeline changes and a real-media integration test for adapter changes. Don't introduce cloud calls, vendor binaries, telemetry, AI model downloads or new runtime dependencies without an explicit architecture decision.

Never commit video/audio samples containing personal, confidential or copyrighted material without permission.
