from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class WorkflowSyntaxTests(unittest.TestCase):
    def test_all_workflows_are_valid_yaml_mappings(self):
        workflow_dir = ROOT / ".github" / "workflows"
        for path in workflow_dir.glob("*.yml"):
            with self.subTest(path=path.name):
                parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIsInstance(parsed, dict)
                self.assertIn("jobs", parsed)


class QuarkSignInWorkflowTests(unittest.TestCase):
    """Lock in the notification behaviour of the sign-in workflow."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / ".github" / "workflows" / "quark_signin.yml"
        cls.workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls.steps = cls.workflow["jobs"]["sign-in"]["steps"]

    def test_cache_hit_still_sends_receipt(self):
        receipts = [s for s in self.steps if s.get("name") == "今日已完成签到回执"]
        self.assertEqual(len(receipts), 1, "缺少缓存命中回执步骤")
        step = receipts[0]
        self.assertIn("cache-hit == 'true'", step["if"])
        self.assertIn("pushplus.py", step["run"])

    def test_receipt_failure_does_not_fail_the_run(self):
        step = next(s for s in self.steps if s.get("name") == "今日已完成签到回执")
        self.assertIn("|| echo", step["run"])

    def test_receipt_step_runs_after_checkout(self):
        names = [s.get("name") for s in self.steps]
        self.assertLess(names.index("检出代码"), names.index("今日已完成签到回执"))
        checkout = next(s for s in self.steps if s.get("name") == "检出代码")
        self.assertNotIn("if", checkout, "检出代码需无条件执行，否则回执步骤拿不到 pushplus.py")

    def test_signin_and_fallback_still_skip_when_cached(self):
        for name in ("执行签到脚本", "失败兜底通知"):
            step = next(s for s in self.steps if s.get("name") == name)
            self.assertIn("cache-hit != 'true'", step["if"])


if __name__ == "__main__":
    unittest.main()
