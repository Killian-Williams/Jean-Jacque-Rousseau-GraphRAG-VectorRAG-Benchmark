"""Create isolated, fingerprinted runs; paid stages require --allow-api."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid

from prepare_data import prepare, verify

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("index-vector", "index-graph", "sample", "answers", "evaluate", "analyze")


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def hashes(paths, root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def tree_hash(path):
    files = hashes(path.rglob("*"), path)
    if not files:
        raise ValueError(f"Empty index: {path}")
    value = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"id": "sha256:" + value, "files": files}


def chroma_content_hash(path):
    """Ignore SQLite layout and Chroma's acquire_write lock bookkeeping only."""
    def cell(value):
        return {"bytes": value.hex()} if isinstance(value, bytes) else value
    with closing(sqlite3.connect((path / "chroma.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        tables = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name == "acquire_write":
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            rows = [json.dumps([cell(v) for v in row], sort_keys=True, separators=(",", ":"))
                    for row in db.execute("SELECT * FROM " + quoted)]
            tables[name] = sorted(rows)
    files = hashes((p for p in path.rglob("*") if p.is_file() and p.name not in
                    {"chroma.sqlite3", "chroma.sqlite3-wal", "chroma.sqlite3-shm", "chroma.sqlite3-journal"}), path)
    content = {"schema": schema, "tables": tables, "files": files}
    return "sha256:" + hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_path(run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Run ID must contain only letters, numbers, underscores, and hyphens")
    path = ROOT / "runs" / run_id
    if path.is_symlink() or path.resolve().parent != (ROOT / "runs").resolve():
        raise ValueError("Unexpected run directory")
    return path


def create(run_id):
    path = run_path(run_id)
    path.mkdir(parents=True, exist_ok=False)
    for name in ("RAG application", "benchmark", "scripts", "prompts"):
        (path / name).mkdir()
        patterns = ("*.py",) if name != "prompts" else ("*.txt",)
        for pattern in patterns:
            for source in (ROOT / name).glob(pattern):
                shutil.copyfile(source, path / name / source.name)
    shutil.copytree(ROOT / "RAG application/data", path / "RAG application/data")
    for name in ("settings.yaml", "requirements.txt"):
        shutil.copyfile(ROOT / name, path / name)
    shutil.copyfile(ROOT / "benchmark/questions.json", path / "benchmark/questions.json")
    corpus = prepare(path)
    tracked = [p for p in path.rglob("*") if p.is_file()]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"schema_version": 1, "run_id": run_id, "created_at": now(),
                "source_commit": commit, "source_worktree_dirty": bool(subprocess.check_output(
                    ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip()),
                "corpus": corpus, "snapshot_sha256": hashes(tracked, path), "stages": {}, "indexes": {},
                "verification_scope": "Identical prepared input bytes; source editions and grounding require separate human verification."}
    save(path / "run.json", manifest)
    print(f"Created {path}\nRun ID: {run_id}\nNo API calls made.")
    return path


def verify_snapshot(path, manifest):
    verify(path)
    for name, expected in manifest["snapshot_sha256"].items():
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Run snapshot changed: {name}; create a new run")
    for stage, directory in (("index-vector", "chroma_db"), ("index-graph", "output")):
        if stage not in manifest["indexes"]:
            continue
        expected = manifest["indexes"][stage]
        if stage == "index-vector" and "content_id" in expected:
            if chroma_content_hash(path / directory) != expected["content_id"]:
                raise ValueError("Chroma indexed content changed after build")
        else:
            if tree_hash(path / directory) != expected:
                raise ValueError(f"Index changed after build: {directory}; create a new run")
            if stage == "index-vector":
                # Establish the logical fingerprint only while original bytes still match.
                expected["content_id"] = chroma_content_hash(path / directory)
    for record in manifest["stages"].values():
        for name, expected in record.get("artifact_sha256", {}).items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Completed-stage artifact changed: {name}")


def verify_index_corpus(path, stage, manifest):
    expected = {r["filename"]: r["prepared_sha256"] for r in manifest["corpus"]["files"]}
    if stage == "index-graph":
        import pyarrow.parquet as pq
        rows = pq.read_table(path / "output/documents.parquet", columns=["title", "text"]).to_pylist()
        actual = {r["title"]: hashlib.sha256(r["text"].encode("utf-8")).hexdigest() for r in rows}
        if len(rows) != len(expected) or actual != expected:
            raise ValueError("GraphRAG document text does not match the prepared corpus")
    else:
        uri = (path / "chroma_db/chroma.sqlite3").as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            rows = db.execute("SELECT s.string_value, h.string_value FROM embedding_metadata s "
                              "JOIN embedding_metadata h ON s.id=h.id "
                              "WHERE s.key='source' AND h.key='source_sha256'").fetchall()
        if not rows or {name for name, sha in rows} != set(expected) or any(expected.get(name) != sha for name, sha in rows):
            raise ValueError("Chroma source metadata does not match the prepared corpus")


def execute(path, stage, allow_api=False):
    if stage != "analyze" and not allow_api:
        raise ValueError("This stage makes paid API calls. Explicitly pass --allow-api when ready.")
    manifest = json.loads((path / "run.json").read_text(encoding="utf-8"))
    verify_snapshot(path, manifest)
    if stage in manifest["stages"]:
        raise ValueError("Stage already attempted. Preserve this run and create a new run rather than mixing attempts.")
    prerequisites = {"sample": ("index-vector", "index-graph"),
                     "answers": ("index-vector", "index-graph"),
                     "evaluate": ("answers",), "analyze": ("evaluate",)}
    for dependency in prerequisites.get(stage, ()):
        if manifest["stages"].get(dependency, {}).get("status") != "completed":
            raise ValueError(f"Complete {dependency} first")
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if stage != "analyze":
        from dotenv import dotenv_values
        # Do not copy credentials into the run snapshot or manifest.
        for key in ("OPENAI_API_KEY", "GRAPHRAG_API_KEY", "JUDGE_MODEL", "JUDGE_RUNS"):
            value = env.get(key) or dotenv_values(ROOT / ".env").get(key)
            if value:
                env[key] = value
        for key in ("OPENAI_API_KEY", "GRAPHRAG_API_KEY"):
            if not env.get(key, "").strip():
                raise ValueError(f"Missing {key} in environment or project .env")
        installed = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
        environment = {"python": sys.version, "packages": installed.splitlines()}
        if "environment" in manifest and environment != manifest["environment"]:
            raise ValueError("Python/package environment changed during run")
        manifest["environment"] = environment
        judge = {"model": env.get("JUDGE_MODEL", "gpt-4.1-mini"), "runs": env.get("JUDGE_RUNS", "3")}
        if "judge" in manifest and judge != manifest["judge"]:
            raise ValueError("Judge configuration changed during run")
        manifest["judge"] = judge
    graph = shutil.which("graphrag", path=env["PATH"])
    if stage in ("index-graph", "sample", "answers") and not graph:
        raise ValueError("GraphRAG CLI is missing; install requirements in this environment")
    commands = {
        "index-vector": [[sys.executable, "RAG application/ingest.py"]],
        "index-graph": [[graph, "index", "--root", str(path)]],
        "sample": [[sys.executable, "-c", "import sys; sys.path.insert(0, 'RAG application'); from rag_chain import ask_rag; print(ask_rag('What does Rousseau mean by the general will?'))"],
                   [graph, "query", "What does Rousseau mean by the general will?", "--root", str(path), "--method", "global"]],
        "answers": [[sys.executable, "benchmark/run_vector_rag.py"], [sys.executable, "benchmark/run_graphrag.py"]],
        "evaluate": [[sys.executable, "benchmark/evaluate.py"]],
        "analyze": [[sys.executable, "-I", "-S", "benchmark/analysis.py"]],
    }
    record = {"status": "running", "started_at": now(), "commands": commands[stage]}
    executor = Path(__file__)
    executor_hash = hashlib.sha256(executor.read_bytes()).hexdigest()
    revision = path / "execution-revisions" / (executor_hash + ".py")
    revision.parent.mkdir(exist_ok=True)
    if not revision.exists():
        shutil.copyfile(executor, revision)
    record["executor_sha256"] = executor_hash
    record["executor_archive"] = revision.relative_to(path).as_posix()
    manifest["stages"][stage] = record
    save(path / "run.json", manifest)
    try:
        for number, command in enumerate(commands[stage]):
            with (path / f"{stage}-{number}.log").open("w", encoding="utf-8") as log:
                subprocess.run(command, cwd=path, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        if stage.startswith("index-"):
            verify_index_corpus(path, stage, manifest)
            directory = "chroma_db" if stage == "index-vector" else "output"
            manifest["indexes"][stage] = tree_hash(path / directory)
        if stage in ("answers", "evaluate"):
            names = ["vector_answers.json", "graphrag_answers.json"] if stage == "answers" else ["evaluations.json"]
            for name in names:
                output = path / "benchmark" / name
                data = json.loads(output.read_text(encoding="utf-8"))
                if stage == "answers":
                    questions = json.loads((path / "benchmark/questions.json").read_text(encoding="utf-8"))["questions"]
                    expected_ids = {q["id"] for q in questions}
                    answer_ids = [r["question_id"] for r in data["results"]]
                    if len(answer_ids) != len(expected_ids) or set(answer_ids) != expected_ids:
                        raise ValueError(f"Incomplete or duplicate question IDs in {name}")
                    if any(r.get("error") or not r.get("answer") for r in data["results"]):
                        raise ValueError(f"Generation errors in {name}; inspect the run logs")
                else:
                    expected = len(json.loads((path / "benchmark/questions.json").read_text())["questions"]) * 4 * int(manifest["judge"]["runs"])
                    if sum(r.get("status") == "completed" for r in data["evaluations"]) != expected:
                        raise ValueError("Evaluation incomplete; inspect the run logs")
                data["provenance"] = {"run_id": manifest["run_id"], "corpus_id": manifest["corpus"]["corpus_id"],
                                      "index_ids": {k: v["id"] for k, v in manifest["indexes"].items()},
                                      "index_content_ids": {k: v.get("content_id", v["id"]) for k, v in manifest["indexes"].items()},
                                      "source_commit": manifest["source_commit"],
                                      "snapshot_sha256": manifest["snapshot_sha256"]}
                save(output, data)
            if stage == "evaluate":
                from check_repository import check_benchmark
                check_benchmark(path)
        record["status"] = "completed"
        record["artifact_sha256"] = hashes((path / "benchmark").rglob("*.json"), path)
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        raise
    finally:
        record["finished_at"] = now()
        save(path / "run.json", manifest)
    print(f"Completed {stage}; logs and metadata in {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("create",) + STAGES)
    parser.add_argument("--run-id")
    parser.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    if args.stage == "create":
        create(args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    elif not args.run_id:
        parser.error("--run-id is required")
    else:
        execute(run_path(args.run_id), args.stage, args.allow_api)
