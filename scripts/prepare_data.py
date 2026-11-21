"""Prepare identical UTF-8/LF input for both systems; no downloads or APIs."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILENAMES = ("Social_Contract.txt", "discourse.txt", "emile.txt")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(root=ROOT):
    source = root / "RAG application" / "data"
    target = root / "input"
    files = []
    for name in FILENAMES:
        original = (source / name).read_bytes()
        text = original.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise ValueError(f"Empty corpus file: {name}")
        files.append((name, original, text.encode("utf-8")))
    if target.exists():
        extras = {p.relative_to(target).as_posix() for p in target.rglob("*.txt")} - set(FILENAMES)
        if extras:
            raise ValueError(f"Unexpected GraphRAG input texts; move them out first: {sorted(extras)}")
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for name, original, prepared in files:
        (target / name).write_bytes(prepared)
        records.append({"filename": name, "source_sha256": digest(original),
                        "prepared_sha256": digest(prepared), "bytes": len(prepared)})
    corpus_id = digest(json.dumps([{k: r[k] for k in ("filename", "prepared_sha256")} for r in records],
                                 sort_keys=True, separators=(",", ":")).encode())
    manifest = {"schema_version": 1, "corpus_id": "sha256:" + corpus_id,
                "preprocessing": "Decode UTF-8 with optional BOM; normalize CRLF/CR to LF; preserve all remaining text.",
                "edition_verification": "Not established; these are the repository's prepared selections, not certified complete editions.",
                "files": records}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify(root)
    return manifest


def verify(root=ROOT):
    target = root / "input"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    expected = {r["filename"] for r in manifest["files"]}
    if expected != set(FILENAMES):
        raise ValueError("Prepared manifest filenames do not match the declared corpus")
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*.txt")}
    if actual != expected:
        raise ValueError("Prepared input has missing or extra text files")
    for row in manifest["files"]:
        data = (target / row["filename"]).read_bytes()
        if digest(data) != row["prepared_sha256"] or len(data) != row["bytes"]:
            raise ValueError(f"Prepared input changed: {row['filename']}; rerun preparation and rebuild indexes")
    rows = [{k: r[k] for k in ("filename", "prepared_sha256")} for r in manifest["files"]]
    identifier = "sha256:" + digest(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())
    if identifier != manifest["corpus_id"]:
        raise ValueError("Corpus identifier does not match manifest contents")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = verify() if args.check else prepare()
    print(f"Verified {len(result['files'])} files: {result['corpus_id']}")
