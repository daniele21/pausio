"""Validate Agent Skills manifests using only the Python standard library.

This is static validation, not an agent behavior or media-quality evaluation.
Usage: python scripts/validate_skills.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SKILLS = frozenset(
    {
        "pausio-python-architecture",
        "pausio-media-ffmpeg",
        "pausio-natural-editing",
        "pausio-speech-ai",
        "pausio-subtitles",
        "pausio-test-engineering",
        "pausio-security-release",
        "pausio-pr-review",
        "pausio-product-ux",
        "pausio-ui-design-system",
        "pausio-video-interaction-ux",
        "pausio-ui-quality",
        "pausio-edit-command-schema",
        "pausio-network-abuse-defense",
        "pausio-mcp-trust-boundary",
        "pausio-input-media-defense",
        "pausio-actions-runner-security",
        "pausio-visual-motion-effects",
    }
)
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Skill-local Markdown links to reference files only. External links are not validated.
REF_PATTERN = re.compile(r"\[[^\]]+\]\((references/[^)\s#]+)(?:#[^)]*)?\)")


def validate_skill(skill_dir: Path) -> list[str]:
    """Validate a single SKILL.md; return actionable problems."""
    problems: list[str] = []
    manifest = skill_dir / "SKILL.md"
    if not manifest.is_file():
        return [f"{manifest}: missing manifest"]

    content = manifest.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return [f"{manifest}: expected opening YAML frontmatter delimiter"]
    end = content.find("\n---\n", 4)
    if end < 0:
        return [f"{manifest}: expected closing YAML frontmatter delimiter"]

    metadata: dict[str, str] = {}
    for lineno, line in enumerate(content[4:end].splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*):\s*(\S.*?)\s*", line)
        if match is None:
            problems.append(f"{manifest}:{lineno}: invalid simple metadata key/value")
            continue
        key, value = match.group(1), match.group(2)
        if key in metadata:
            problems.append(f"{manifest}:{lineno}: duplicate metadata key {key!r}")
        metadata[key] = value.strip().strip("\"'")

    name, description = metadata.get("name", ""), metadata.get("description", "")
    if not NAME_PATTERN.fullmatch(name) or len(name) > 64:
        problems.append(f"{manifest}: invalid skill name {name!r}")
    if name != skill_dir.name:
        problems.append(f"{manifest}: name must match directory {skill_dir.name!r}")
    if not 1 <= len(description) <= 1024:
        problems.append(f"{manifest}: description must contain 1..1024 characters")
    if len(content[end + 5:].strip()) < 100:
        problems.append(f"{manifest}: skill body too short")

    for relative_path in REF_PATTERN.findall(content[end + 5:]):
        ref = (skill_dir / relative_path).resolve()
        if not ref.is_relative_to(skill_dir.resolve()):
            problems.append(f"{manifest}: reference escapes directory: {relative_path}")
        elif not ref.is_file():
            problems.append(f"{manifest}: missing referenced file: {relative_path}")
    return problems


def validate_repository(repo: Path = REPO_ROOT) -> list[str]:
    root = repo / ".agents" / "skills"
    if not root.is_dir():
        return [f"{root}: missing skills directory"]
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    present = {p.name for p in dirs}
    problems = [f"{root}: missing required skill: {name}" for name in sorted(REQUIRED_SKILLS - present)]
    for directory in dirs:
        problems.extend(validate_skill(directory))

    for doc in ("AGENTS.md", "CLAUDE.md", "docs/AGENT_SKILLS.md"):
        if not (repo / doc).is_file():
            problems.append(f"{repo / doc}: missing index")
    agents = repo / "AGENTS.md"
    if agents.is_file():
        index = agents.read_text(encoding="utf-8")
        for name in sorted(REQUIRED_SKILLS):
            if name not in index:
                problems.append(f"{agents}: missing skill route: {name}")
    return problems


def main() -> int:
    issues = validate_repository()
    if issues:
        for problem in issues:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print(f"Validated {len(REQUIRED_SKILLS)} Pausio Agent Skills and references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
