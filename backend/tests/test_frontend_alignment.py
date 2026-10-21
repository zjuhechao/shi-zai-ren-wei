"""Regression wrapper that runs verify_frontend_calc.cjs to keep the browser
offline formulas aligned with calculators.py. Node must be on PATH or available
via the platform launcher."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPT = TESTS_DIR / "verify_frontend_calc.cjs"


def _node_candidates() -> list[str]:
    return [c for c in ("node",) if shutil.which(c)]


class FrontendCalculationAlignmentTests(unittest.TestCase):
    def test_browser_formulas_match_python_calculators(self) -> None:
        node = next((c for c in _node_candidates()), None)
        if node is None:
            self.skipTest("Node.js 不可用，跳过前端口径对齐测试")
        result = subprocess.run(
            [node, str(SCRIPT)],
            cwd=str(TESTS_DIR.parents[1]),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, msg=f"前端口径漂移：\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
