import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checks", ROOT / "scripts/check_repository.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class IntegrityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_missing_drift_prompt_fails(self):
        shutil.copytree(ROOT / "prompts", self.root / "prompts")
        settings = (ROOT / "settings.yaml").read_text(encoding="utf-8")
        self.assertIn('prompts/drift_reduce_prompt.txt', settings)
        (self.root / "settings.yaml").write_text(settings.replace('prompts/drift_reduce_prompt.txt', 'prompts/drift_reduce_missing.txt'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing or case-mismatched prompt"):
            checks.check_prompts(self.root)

    def test_duplicate_answer_id_fails(self):
        shutil.copytree(ROOT / "benchmark", self.root / "benchmark")
        path = self.root / "benchmark/vector_answers.json"
        data = checks.load(path)
        data["results"][1]["question_id"] = data["results"][0]["question_id"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "answer IDs"):
            checks.check_benchmark(self.root)

    def test_stale_summary_fails(self):
        shutil.copytree(ROOT / "benchmark", self.root / "benchmark")
        path = self.root / "benchmark/analysis_results/summary.json"
        data = checks.load(path)
        data["overall"]["graphrag_wins"] = -1
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Stale saved summary"):
            checks.check_summaries(self.root)


if __name__ == "__main__":
    unittest.main()
