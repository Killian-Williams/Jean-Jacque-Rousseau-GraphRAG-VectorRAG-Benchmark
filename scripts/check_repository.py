"""Offline integrity checks. Run with Python 3.12; no API keys required."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, f"{path}: duplicate JSON key {key}")
            obj[key] = value
        return obj
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def check_prompts(root):
    # Configuration uses one quoted/plain scalar per prompt key. Reject other
    # forms explicitly rather than silently skipping an unrecognized path.
    paths = []
    for line in (root / "settings.yaml").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(\w*prompt)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match[2].split(" #", 1)[0].strip().strip("\"'")
        require(value.startswith("prompts/") and "\\" not in value,
                f"Unsupported prompt path: {line}")
        parts = Path(value).parts
        require(".." not in parts, f"Prompt path escapes repository: {value}")
        path = root
        for part in parts:
            require(part in {p.name for p in path.iterdir()},
                    f"Missing or case-mismatched prompt: {value}")
            path /= part
        require(path.is_file() and path.read_text(encoding="utf-8").strip(),
                f"Empty or invalid prompt: {value}")
        paths.append(value)
    require(paths, "No configured prompt paths found")


def check_benchmark(root):
    folder = root / "benchmark"
    questions = load(folder / "questions.json")
    name = questions["benchmark_name"]
    rows = questions["questions"]
    require(isinstance(rows, list) and rows, "Questions must be a nonempty list")
    by_id = {}
    for row in rows:
        qid = row["id"]
        require(isinstance(qid, str) and qid and qid not in by_id,
                f"Invalid or duplicate question ID: {qid}")
        require(isinstance(row["question"], str) and row["question"].strip(), f"Empty question: {qid}")
        by_id[qid] = row
    require(questions["design"]["total_questions"] == len(rows), "Question count mismatch")
    counts = {category: sum(q["category"] == category for q in rows)
              for category in questions["design"]["categories"]}
    require(counts == questions["design"]["categories"] and sum(counts.values()) == len(rows),
            "Question category counts mismatch")
    for filename, system in [("vector_answers.json", "vector_rag"), ("graphrag_answers.json", "graphrag")]:
        data = load(folder / filename)
        require(data["benchmark_name"] == name and data["system"] == system, f"Benchmark/system mismatch: {filename}")
        results = data["results"]
        ids = [r["question_id"] for r in results]
        require(len(ids) == len(set(ids)) and set(ids) == set(by_id), f"Missing/duplicate/unexpected answer IDs: {filename}")
        require(data["total_completed"] == len(results), f"Answer count mismatch: {filename}")
        for row in results:
            q = by_id[row["question_id"]]
            require(row["question"] == q["question"] and row["category"] == q["category"], f"Question mismatch: {filename}/{q['id']}")
            require(row["system"] == system, f"Wrong answer system: {filename}")
            require(row["error"] is None and isinstance(row["answer"], str) and row["answer"].strip(), f"Failed/empty saved answer: {filename}/{q['id']}")
            latency = row["latency_seconds"]
            require(type(latency) in (int, float) and math.isfinite(latency) and latency >= 0, f"Invalid latency: {filename}")
    data = load(folder / "evaluations.json")
    require(data["benchmark_name"] == name, "Evaluation benchmark name mismatch")
    criteria = {"comprehensiveness", "diversity", "empowerment", "directness"}
    require(set(data["criteria"]) == criteria and len(data["criteria"]) == 4, "Invalid evaluation criteria")
    runs = data["judge_runs_per_criterion"]
    require(type(runs) is int and runs > 0, "Invalid judge run count")
    require(data["total_evaluations"] == len(data["evaluations"]), "Evaluation count mismatch")
    completed = set()
    for row in data["evaluations"]:
        qid = row["question_id"]
        require(qid in by_id, f"Unknown evaluation ID: {qid}")
        require(row["question"] == by_id[qid]["question"] and row["category"] == by_id[qid]["category"], f"Evaluation question mismatch: {qid}")
        require(row["criterion"] in criteria and type(row["run_number"]) is int and 1 <= row["run_number"] <= runs, f"Invalid evaluation key: {qid}")
        require(row["status"] in {"completed", "error", "skipped"}, f"Invalid status: {qid}")
        if row["status"] == "completed":
            key = (qid, row["criterion"], row["run_number"])
            require(key not in completed, f"Duplicate completed judgment: {key}")
            completed.add(key)
            require({row["answer_1_system"], row["answer_2_system"]} == {"vector_rag", "graphrag"}, f"Invalid answer ordering: {key}")
            winner = row["judge_winner"]
            require(type(winner) is int and winner in (0, 1, 2), f"Invalid winner: {key}")
            expected = "tie" if winner == 0 else row[f"answer_{winner}_system"]
            require(row["winner_system"] == expected and row["error"] is None, f"Winner mapping mismatch: {key}")
            require(isinstance(row["reasoning"], str) and row["reasoning"].strip(), f"Missing reasoning: {key}")
    expected = {(qid, criterion, run) for qid in by_id for criterion in criteria for run in range(1, runs + 1)}
    require(completed == expected, "Saved evaluation has incomplete judgment coverage")


def check_summaries(root):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "benchmark"
        folder.mkdir()
        for name in ["analysis.py", "questions.json", "vector_answers.json", "graphrag_answers.json", "evaluations.json"]:
            shutil.copyfile(root / "benchmark" / name, folder / name)
        # -I -S disables site packages, including API SDKs and optional charts.
        subprocess.run([sys.executable, "-I", "-S", str(folder / "analysis.py")],
                       check=True, capture_output=True, text=True)
        generated = folder / "analysis_results"
        expected = root / "benchmark" / "analysis_results"
        names = {p.name for p in generated.iterdir() if p.suffix in {".csv", ".json"}}
        require(names == {p.name for p in expected.iterdir() if p.suffix in {".csv", ".json"}}, "Summary artifact set mismatch")
        for name in sorted(names):
            if name.endswith(".json"):
                same = load(generated / name) == load(expected / name)
            else:
                def rows(path):
                    return list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
                same = rows(generated / name) == rows(expected / name)
            require(same, f"Stale saved summary: {name}; run python benchmark/analysis.py and commit the outputs")


def check_release(root):
    manifest = load(root / "benchmark" / "release-manifest.json")
    require(manifest["release_tag"] and manifest["snapshot_id"], "Missing release identifiers")
    for name, expected in manifest["artifact_sha256"].items():
        # Hash normalized text to remain stable under Git's CRLF checkout conversion.
        data = (root / name).read_text(encoding="utf-8").encode("utf-8")
        require(hashlib.sha256(data).hexdigest() == expected, f"Release artifact changed: {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    for check in (check_prompts, check_benchmark, check_summaries, check_release):
        check(args.root)
        print(f"PASS: {check.__name__}")


if __name__ == "__main__":
    main()
