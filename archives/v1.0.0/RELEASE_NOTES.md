# v1.0.0 — Saved benchmark results and offline validation

This release preserves the current 60-question Vector RAG versus Microsoft GraphRAG global-search comparison, including saved answers, judge evaluations, regenerated summaries, and artifact fingerprints.

## Results

- GraphRAG wins 222 of 240 question-and-criterion majority decisions (92.50%); vector RAG wins 18 (7.50%).
- GraphRAG wins by criterion: comprehensiveness 60/60, diversity 60/60, empowerment 57/60, directness 45/60.
- Mean recorded latency: vector RAG 6.971 seconds; GraphRAG 656.376 seconds.
- The saved evaluations contain 720 completed judgments and 13 error records. Errors are excluded from majority voting.

The previously committed summaries described a different artifact set (77.08% overall GraphRAG preference). This release regenerates the summaries from the current saved evaluations; it does not rerun paid answer generation or judging.

## Validation

GitHub Actions checks prompt paths (including DRIFT), benchmark names and question IDs, answer/evaluation structure and coverage, regeneration of JSON/CSV summaries, and artifact fingerprints. Regression tests verify that missing prompts, duplicate answer IDs, and stale summaries fail validation. All checks use Python 3.12's standard library without API keys.

```shell
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

## Scope and limitations

This is a saved-results snapshot, not a certification of end-to-end generation reproducibility. The original execution run identifier and index-to-answer linkage were not recorded. Surviving local indexes contain `reveries.txt`, and equivalence of the published systems' historical corpora remains unverified. Judge preferences are not factual-accuracy or faithfulness scores. Full installation, index rebuilding, and live API generation have not been verified end to end for this release.

The tag identifies the source commit. `benchmark/release-manifest.json` fingerprints the saved artifacts using normalized-text SHA-256 hashes. `corpus-manifest.json` and `CORPUS_PROVENANCE.md` document retrospective observations and unresolved provenance. The snapshot identifier is retrospective and must not be represented as an original execution run ID.

Code license: Apache-2.0. Source-text attribution and applicable notices are documented separately in `SOURCES.md`.
