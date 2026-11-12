"""Fail-closed guard for security-dangerous workflow patterns in public Pausio.

This is a narrow security policy check (no PyYAML dependency), not a complete
GitHub Actions YAML validator. A private ASR runner MUST live in another repo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTED_RUNNER = re.compile(r"^(?:ubuntu|windows|macos)-(?:latest|[0-9][a-zA-Z0-9.-]*)$")


def issues_in_workflow(name: str, content: str) -> list[str]:
    # We only inspect non-comment lines; this is intentionally conservative.
    lines = [line for line in content.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    text = "\n".join(lines)
    errors = []
    if re.search(r"(?m)^permissions:\s*(?:write-all|read-all)\s*$", text):
        errors.append("broad permissions: write-all/read-all are forbidden")
    if not re.search(r"(?m)^permissions:\s*(?:$|\{)", text):
        errors.append("missing explicit top-level permissions")
    if re.search(r"(?m)^\s*(?:pull_request_target|workflow_run)\s*:", text):
        errors.append("privileged pull_request_target/workflow_run triggers forbidden")
    if re.search(r"\bself-hosted\b", text, re.IGNORECASE):
        errors.append("self-hosted runners forbidden in the public repository")
    for line in lines:
        m = re.match(r"^\s*runs-on:\s*(.+?)\s*$", line)
        if m and not HOSTED_RUNNER.fullmatch(m.group(1)):
            errors.append("dynamic/non-hosted runs-on label is not approved: " + m.group(1)[:80])
    return [name + ": " + item for item in errors]


def validate_repository(root: Path = ROOT) -> list[str]:
    directory = root / ".github" / "workflows"
    workflows = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    if not workflows:
        return ["missing GitHub Actions workflows"]
    errors = []
    for path in workflows:
        errors.extend(issues_in_workflow(path.name, path.read_text(encoding="utf-8")))
    return errors


def main() -> int:
    issues = validate_repository()
    if issues:
        for issue in issues:
            print("SECURITY ERROR:", issue, file=sys.stderr)
        return 1
    print("Verified GitHub Actions public-repo workflow policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
