"""Policy regression tests for public Pausio GitHub Actions."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_security_workflows.py"
spec = importlib.util.spec_from_file_location("pausio_actions_policy", CHECKER)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ActionsSecurityPolicyTests(unittest.TestCase):
    def test_repository_uses_only_hosted_runners_and_restricted_triggers(self):
        self.assertEqual(module.validate_repository(), [])

    def test_cannot_route_public_prs_to_self_hosted_mac(self):
        example = """name: danger
on:
  pull_request:
permissions:
  contents: read
jobs:
  run:
    runs-on: [self-hosted, macOS]
"""
        problems = module.issues_in_workflow("untrusted.yml", example)
        self.assertTrue(any("self-hosted" in p for p in problems), problems)
        self.assertTrue(any("runs-on" in p for p in problems), problems)

    def test_disallows_privileged_triggers_and_write_all(self):
        example = """name: danger
on:
  pull_request_target:
  workflow_run:
permissions: write-all
jobs:
  bad:
    runs-on: ubuntu-latest
"""
        problems = module.issues_in_workflow("danger.yml", example)
        self.assertTrue(any("trigger" in p for p in problems))
        self.assertTrue(any("permissions" in p for p in problems))

    def test_disallows_dynamic_runner_labels(self):
        example = """name: danger
on: push
permissions:
  contents: read
jobs:
  bad:
    runs-on: ${{ inputs.runner }}
"""
        problems = module.issues_in_workflow("dynamic.yml", example)
        self.assertTrue(any("runs-on" in p for p in problems), problems)

    def test_accepts_minimally_privileged_hosted_pages(self):
        example = """name: pages
on:
  push:
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  publish:
    runs-on: ubuntu-latest
"""
        self.assertEqual(module.issues_in_workflow("pages.yml", example), [])

    def test_fails_on_missing_permissions(self):
        problems = module.issues_in_workflow("missing.yml",
                                             "name: one\njobs:\n  a:\n    runs-on: ubuntu-latest\n")
        self.assertTrue(any("permissions" in p for p in problems))

    def test_noncomment_lines_only(self):
        example = """# self-hosted is forbidden
name: CI
on: push
permissions:
  contents: read
jobs:
  hosted:
    runs-on: ubuntu-latest
"""
        self.assertEqual(module.issues_in_workflow("safe.yml", example), [])


if __name__ == "__main__":
    unittest.main()
