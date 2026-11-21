from pathlib import Path
import shutil

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "RAG application" / "data"
INPUT_DIR = PROJECT_DIR / "input"
FILENAMES = ("Social_Contract.txt", "emile.txt", "discourse.txt")


def main():
    files = [SOURCE_DIR / name for name in FILENAMES]
    for path in files:
        if not path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Empty source document: {path}")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    extras = {p.name for p in INPUT_DIR.glob("*.txt")} - set(FILENAMES)
    if extras:
        raise ValueError(f"Move unrelated input texts out of input/: {sorted(extras)}")

    for path in files:
        destination = INPUT_DIR / path.name
        shutil.copyfile(path, destination)
        print(f"Prepared {destination.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
```

This keeps both systems on the same prepared corpus. If you change corpus filenames, update this list too.

## 6. Add the following quick start to the README

The commands below assume the edits above have been committed. Place this section before your configuration details.

---

## Quick start

Use Python **3.12** (the original project environment used 3.12.10) and Git. Run all commands from the repository root, which contains `settings.yaml` and `benchmark/`. Indexing, question answering, and LLM evaluation use paid API calls. Analyzing saved results does not.

### Clone and install

```shell
git clone https://github.com/Killian-Williams/Jean-Jacque-Rousseau-GraphRAG-VectorRAG-Benchmark.git
cd Jean-Jacque-Rousseau-GraphRAG-VectorRAG-Benchmark
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Then, in either shell:

```shell
python -m pip install -r requirements.txt
python -m pip check
```

Keep this environment activated for the remaining commands, including those that invoke `graphrag`.



```shell
python -m pip install -r requirements.txt
python -m pip check
```

Keep this environment activated for the remaining commands, including those that invoke `graphrag`.

### Analyze the published outputs without an API key

```shell
python benchmark/analysis.py
```

This reads the committed outputs and writes CSV/JSON summaries to `benchmark/analysis_results/`. This step can also run before dependency installation: it needs only Python's standard library. Charts are optional and are skipped if `matplotlib` is absent.

### Configure credentials

Copy the template without overwriting an existing `.env`:

```shell
python -c "from pathlib import Path; p=Path('.env'); p.exists() or p.write_bytes(Path('.env.example').read_bytes())"
```

Open `.env` in your editor and fill in both `OPENAI_API_KEY` and `GRAPHRAG_API_KEY`. Leave the example file's credentials blank. Keep the judge defaults to match the benchmark's evaluation configuration.

### Prepare the corpus

```shell
python scripts/prepare_data.py
```

Expected layout:

```text
RAG application/data/           input/
  Social_Contract.txt             Social_Contract.txt
  emile.txt                      emile.txt
  discourse.txt                  discourse.txt
```

Vector RAG reads the left directory; GraphRAG reads the right directory. The copy preserves the prepared files byte for byte. See [SOURCES.md](SOURCES.md) for attribution. Copying the committed prepared corpus does not reproduce the earlier manual text-cleaning process.

### Build both indexes — paid API calls

```shell
python "RAG application/ingest.py"
graphrag index --root .
```

The first command rebuilds `chroma_db/`. GraphRAG writes its index under `output/`, including Parquet files and `output/lancedb/`, with logs in `logs/` and cached responses in `cache/`. The repository already supplies GraphRAG configuration and prompts; no initialization command is needed.

### Ask a sample question — paid API calls

Start the vector chatbot:

```shell
python "RAG application/app.py"
```

Enter `What does Rousseau mean by the general will?`, then enter `exit` when finished.

Ask GraphRAG the same question:

```shell
graphrag query "What does Rousseau mean by the general will?" --root . --method global
```

Both commands display their answers in the terminal.

### Generate and evaluate a new benchmark — paid API calls

First archive the existing answer files, evaluations, and summaries. The answer runners overwrite their outputs. The evaluator resumes by question ID, criterion, and run number, so existing judgments must be moved aside when generating new answers.

Windows PowerShell:

```powershell
$archiveDir = Join-Path 'benchmark' ('archive-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $archiveDir | Out-Null
foreach ($name in @('vector_answers.json', 'graphrag_answers.json', 'evaluations.json', 'analysis_results')) {
    $sourcePath = Join-Path 'benchmark' $name
    if (Test-Path -LiteralPath $sourcePath) {
        Move-Item -LiteralPath $sourcePath -Destination $archiveDir
    }
}
```

macOS/Linux:

```bash
archive_dir=$(mktemp -d benchmark/archive-XXXXXXXX)
for name in vector_answers.json graphrag_answers.json evaluations.json analysis_results; do
    if [ -e "benchmark/$name" ]; then
        mv "benchmark/$name" "$archive_dir/"
    fi
done
```

Then run:

```shell
python benchmark/run_vector_rag.py
python benchmark/run_graphrag.py
python benchmark/evaluate.py
python benchmark/analysis.py
```

Expected outputs are `benchmark/vector_answers.json`, `benchmark/graphrag_answers.json`, `benchmark/evaluations.json`, and `benchmark/analysis_results/summary.json`, plus CSV summaries. Inspect answer records for errors before interpreting the evaluation. A script completing does not guarantee every API call succeeded.

Only the last command is offline. With 60 successful answer pairs, four criteria, and three judge runs, a fresh evaluation requests 720 judgments. Archive once before a new experiment; do not archive again when resuming that same evaluation.

### Runtime expectations

Corpus copying and offline analysis should normally take seconds for this dataset. Dependency installation depends on download speed and platform. Indexing and judge-evaluation durations have not been measured reliably. The previously reported benchmark averaged about 5.42 seconds per vector answer and 656.38 seconds per GraphRAG answer, implying roughly 5.4 minutes and 10.9 hours respectively for 60 sequential questions, excluding indexing and evaluation. These figures describe the earlier reported run and are not a promise for a new run.

---

## Verification status and remaining work

A fresh clone of commit `6a97a5e` was created for inspection. Offline analysis succeeded in an isolated Python environment without API credentials or third-party packages. It generated 240 complete majority decisions for 60 questions.

The current committed evaluations produce **92.50% overall GraphRAG preference**, **95% empowerment**, and **75% directness**. The README reports **77.08%**, **83.33%**, and **25%**, respectively. Identify which run you intend to publish and align the saved evaluations, summaries, and README before tagging a release.

Full installation, rebuilding both indexes, live sample questions, and paid evaluation have not been verified end to end. Do not label the entire quick start as tested until these steps pass in a fresh environment after the proposed files are committed. Record the tested commit, Python version, operating system, timings, and any failures.

Add `/benchmark/archive-*/` to `.gitignore` to exclude local experiment backups. If publishing summary files in Git, remove `/benchmark/analysis_results/` from `.gitignore` and commit the intended summaries so README artifact links work after cloning.
