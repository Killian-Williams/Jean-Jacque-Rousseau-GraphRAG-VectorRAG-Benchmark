# Corpus provenance audit

Audit date: 2026-11-21. Repository snapshot: `6a97a5e3c25ca39b269487f1550767a4b6b2dbd2`.

## Finding

**`reveries.txt` was included in both surviving local Rousseau indexes. Its inclusion in the indexes that produced the published answers remains unverified.**

The local GraphRAG `output/documents.parquet` contains a `reveries.txt` document linked to 114 text units. The local root Chroma database contains 748 chunks with `source = reveries.txt`. All 748 stored chunk texts occur verbatim in the surviving local source file. These are index contents, not inferences from a folder listing.

However, the answer artifacts contain no recorded corpus/index fingerprint or original execution identifier. The local Chroma collection is named `spinoza_collection`, whereas the repository configuration uses `rousseau_collection`. The collection name does not invalidate the observed Rousseau chunks, but the discrepancy prevents treating this local database as a verified copy of the published benchmark's database.

Git history records the benchmark answer/evaluation files being added in `ee8ad44`, `reveries.txt` being added in `894606e`, and its deletion in `179d0f6`. These are repository events, not index-build or answer-generation timestamps. Deletion alone does not establish that an index was rebuilt.

## Observed contents

| Evidence | Files or source labels | What is established |
|---|---|---|
| Repository corpus at the audited commit | `discourse.txt`, `emile.txt`, `Social_Contract.txt` | Three files are available for a new build; historical index membership is not established by this list. |
| Surviving GraphRAG document table | `discourse.txt`, `emile.txt`, `hi.txt`, `reveries.txt` | Four documents were included in this local index. |
| Surviving root Chroma database | `discourse.txt` (406 chunks), `emile.txt` (792), `Social_Contract.txt` (1,972), `reveries.txt` (748) | Four source labels occur in this local index. |

The other Chroma database under `RAG application/chroma_db/` contains 1,479 chunks labeled `data/spinoza.txt`; it is a separate local index and should not be used as Rousseau provenance evidence.

## Sections and preprocessing

- `Social_Contract.txt` contains the Social Contract's foreword and Books I–IV, followed by discourses on arts and sciences, inequality, and political economy. Its filename understates its contents.
- GraphRAG's stored `hi.txt` begins with the title *The Social Contract & Discourses*, publisher information, a G. D. H. Cole translation credit, and an introduction. Its stored text differs from the current local `input/hi.txt`.
- Only 1,712 of Chroma's 1,972 `Social_Contract.txt` chunks match exact substrings of the current local source. The remaining differences have not been explained; they could reflect source changes or ingestion transformations. The current file's checksum must not be described as a verified checksum of the historical vector-index input.
- `emile.txt` has headings for Books First, Second, and Third and contains summaries/commentary and notes. Its correspondence to the attributed Barbara Foxley edition has not been established. Do not describe it as a verified complete copy of that edition.
- `reveries.txt` includes an introduction and headings for the First through Tenth Walks. Its exact source edition and translator remain unverified.
- `discourse.txt` begins with the Academy of Dijon's question and contains the inequality discourse, including a Second Part marker.

No reproducible preprocessing script, original-download hashes, or complete edit log was found in the inspected material. The earlier blanket statement that introductions and all non-Rousseau material were removed is contradicted by the surviving indexed text. Observed headings identify content but do not certify complete editions or exact section boundaries.

## Manifest and benchmark identifiers

[corpus-manifest.json](corpus-manifest.json) records filenames, sizes, SHA-256 file checksums, observed sections, preprocessing status, index evidence, and fingerprints of two saved benchmark artifact sets.

The artifact sets have retrospective identifiers:

- Published-file snapshot: `published-files-sha256-18bfddbfde22ca31c3c0e4c64f153144cf224a457ee00219792d09f112c60cbd`.
- Earlier local snapshot: `earlier-local-files-sha256-fd55f7f1ea7a829b5a65628f695a2bac45c3d99c29f987d01bb8a310e0e10f43`.

These identify the inspected questions, answers, and evaluations, **not original execution runs**. `original_benchmark_run_id` is explicitly null. Each set fingerprint hashes its ordered artifact-record list serialized as JSON with sorted keys, no extra whitespace, and UTF-8 encoding.

Raw file checksums hash exact bytes. Stored GraphRAG text checksums hash extracted document strings encoded as UTF-8. These are different hash scopes and must not be compared as if they were the same. Python text comparisons normalize line endings; raw file hashes do not.

Manifest origin `repository_snapshot` refers to the audited Git checkout. `surviving_local_workspace` refers to the inspected Desktop `Rousseau_GraphRAG` directory. The manifest captures observations; its local index evidence is not currently bundled in Git.

## README replacement

Replace claims that both published systems used the same three-work corpus and that all introductions were removed with:

> The repository currently provides three prepared text files for new index builds. Historical corpus provenance is incomplete: surviving local GraphRAG and Chroma indexes both contain `reveries.txt`, and their Social Contract inputs do not match the current files consistently. The saved answers do not identify their original index snapshots, so we cannot confirm the exact corpus or identical preprocessing for the published comparison. See [Corpus provenance](CORPUS_PROVENANCE.md) and the [corpus manifest](corpus-manifest.json) for checksums, observed contents, and unresolved questions.

Retain the numerical results as results of the saved evaluation, but add this limitation:

> Corpus equivalence between the published systems is unverified. Differences in source coverage or preprocessing may contribute to the measured preferences, alongside retrieval architecture and prompting.

## Establishing a fully reproducible future run

Choose the intended works and exact sections, verify their editions, and preserve the original downloads separately from prepared input files. Record the preparation script or edit log and hash the prepared files. Build both indexes from those same files in fresh output directories. Assign an execution run ID before generating answers and record it, the source commit, manifest fingerprint, and index fingerprints in the answer and evaluation metadata. Archive the completed artifacts together.

This audit does not rebuild indexes or make paid API calls. It cannot retroactively recover an execution identifier or certify an index-to-answer relationship that was never recorded.
