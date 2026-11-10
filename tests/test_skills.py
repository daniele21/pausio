"""Regression tests for repo-scoped Agent Skills manifests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_skills import REQUIRED_SKILLS, validate_repository, validate_skill


class SkillsTests(unittest.TestCase):
    def test_catalog_has_all_expected_skills_and_valid_references(self):
        self.assertEqual(validate_repository(), [])

    def test_all_required_skills_are_present(self):
        repo = Path(__file__).resolve().parents[1]
        dirs = {p.name for p in (repo / ".agents" / "skills").iterdir() if p.is_dir()}
        self.assertTrue(REQUIRED_SKILLS.issubset(dirs))

    def test_detects_bad_name_duplicate_key_and_missing_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "test-skill"
            folder.mkdir()
            (folder / "SKILL.md").write_text(
                "---\nname: second\nname: invalid_name\n"
                "description: Use when testing invalid agent skill metadata.\n---\n"
                "# Bad example\n"
                "Always inspect requirements first, write tests for regressions, "
                "validate boundary conditions and review risks before publishing. "
                "See [missing](references/not-there.md).\n",
                encoding="utf-8",
            )
            errors = validate_skill(folder)
        self.assertTrue(any("duplicate metadata" in x for x in errors))
        self.assertTrue(any("invalid skill name" in x for x in errors))
        self.assertTrue(any("missing referenced file" in x for x in errors))

    def test_accepts_good_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "good-skill"
            (folder / "references").mkdir(parents=True)
            (folder / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (folder / "SKILL.md").write_text(
                "---\nname: good-skill\n"
                "description: Use when practicing code-review and testing workflows.\n---\n"
                "# Good example\n"
                "Inspect current code, state the desired contract, write regression tests, "
                "make a focused change, verify negative paths, and document limitations. "
                "See [guide](references/guide.md).\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_skill(folder), [])


if __name__ == "__main__":
    unittest.main()
