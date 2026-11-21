import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_data
import experiment


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = self.root / "RAG application/data"
        source.mkdir(parents=True)
        for name in prepare_data.FILENAMES:
            (source / name).write_bytes(b"\xef\xbb\xbfOne\r\nTwo\rThree\n")

    def test_normalization_and_stable_corpus_id(self):
        first = prepare_data.prepare(self.root)
        second = prepare_data.prepare(self.root)
        self.assertEqual(first, second)
        for name in prepare_data.FILENAMES:
            self.assertEqual((self.root / "input" / name).read_bytes(), b"One\nTwo\nThree\n")

    def test_extra_input_rejected_before_copy(self):
        (self.root / "input").mkdir()
        (self.root / "input/reveries.txt").write_text("Extra work")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            prepare_data.prepare(self.root)
        self.assertFalse((self.root / "input/emile.txt").exists())

    def test_modified_prepared_file_rejected(self):
        prepare_data.prepare(self.root)
        (self.root / "input/emile.txt").write_text("Altered text")
        with self.assertRaisesRegex(ValueError, "changed"):
            prepare_data.verify(self.root)

    def test_paid_stages_require_explicit_flag(self):
        for stage in experiment.STAGES:
            if stage != "analyze":
                with self.assertRaisesRegex(ValueError, "paid API"):
                    experiment.execute(self.root, stage)

    def test_run_id_cannot_escape_workspace(self):
        with self.assertRaises(ValueError):
            experiment.run_path("../outside")

    def test_snapshot_isolation_and_tamper_detection(self):
        for name in ("benchmark", "scripts", "prompts"):
            (self.root / name).mkdir()
        (self.root / "benchmark/questions.json").write_text('{"questions": []}')
        (self.root / "settings.yaml").write_text("input: {}")
        (self.root / "requirements.txt").write_text("example==1.0")
        with patch.object(experiment, "ROOT", self.root), patch.object(
                experiment.subprocess, "check_output", side_effect=["abc123", ""]):
            run = experiment.create("test-run")
        manifest = json.loads((run / "run.json").read_text())
        experiment.verify_snapshot(run, manifest)
        (self.root / "settings.yaml").write_text("Changed outside the snapshot")
        experiment.verify_snapshot(run, manifest)
        (run / "settings.yaml").write_text("Changed inside the snapshot")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            experiment.verify_snapshot(run, manifest)

    def test_completed_output_tampering_is_rejected(self):
        prepare_data.prepare(self.root)
        output = self.root / "answers.json"
        output.write_text("original")
        manifest = {"snapshot_sha256": {}, "indexes": {}, "stages": {
            "answers": {"artifact_sha256": experiment.hashes([output], self.root)}}}
        output.write_text("modified")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            experiment.verify_snapshot(self.root, manifest)


if __name__ == "__main__":
    unittest.main()
