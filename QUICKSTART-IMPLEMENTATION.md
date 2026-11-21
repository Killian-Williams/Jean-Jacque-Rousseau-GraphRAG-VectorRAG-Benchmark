# Quick-start implementation status

The proposed changes have been implemented. Follow the executable [README quick start](README.md#quick-start) for Python 3.12 installation, credentials, identical input preparation, index builds, sample questions, and an isolated benchmark run.

- `.env.example` provides blank credentials.
- `scripts/prepare_data.py` prepares and hashes the same input files for both systems.
- Vector ingestion and storage use project-relative `pathlib` paths.
- `scripts/experiment.py` snapshots a run and records corpus, configuration, index, and output identifiers.
- CI verifies saved artifacts, preparation, dependency installation, and ingestion dry-run without paid API calls.

**Pending:** live index builds, sample questions, and the new 60-question benchmark are deferred until API funding and reliable internet are available. Installation and offline checks do not establish end-to-end live success. Source-edition verification and human review of answer grounding also remain open.

The old proposal is retained in Git history. Current results and their correction are documented in [README](README.md#results) and [release notes](RELEASE_NOTES.md); the v1.0.0 artifact hashes are preserved, with its original settings archived under `benchmark/release-config/v1.0.0/`.
