# Source-text attribution

This project studies retrieval-augmented question answering over works by Jean-Jacques Rousseau. Attribution and exact benchmark provenance are separate: a source link does not prove that a particular edition or section was indexed.

## Attributed sources

| Work | Translator in the maintainer's source record | Source | Verification status |
|---|---|---|---|
| *A Discourse Upon the Origin and the Foundation of the Inequality Among Mankind* | Unknown | [Project Gutenberg, ebook 11136](https://www.gutenberg.org/ebooks/11136) | Exact edition-to-file mapping not independently established. |
| *The Social Contract & Discourses* | G. D. H. Cole | [Project Gutenberg, ebook 46333](https://www.gutenberg.org/ebooks/46333) | Cole is also credited in the surviving GraphRAG document text; the file contains multiple works. |
| *Emile, or Education* | Barbara Foxley | [Online Library of Liberty](https://oll.libertyfund.org/titles/rousseau-emile-or-education) | This is the attributed source, but the prepared file's edition and translator remain unverified; observed headings cover Books First–Third. |
| *Reveries of the Solitary Walker* | Unverified | Not established | `reveries.txt` occurs in both surviving local indexes despite its removal from the repository. |

## Exact corpus and preprocessing

See [CORPUS_PROVENANCE.md](CORPUS_PROVENANCE.md) for the evidence and [corpus-manifest.json](corpus-manifest.json) for filenames, checksums, observed sections, preprocessing gaps, and retrospective benchmark snapshot identifiers.

The surviving local indexes cannot conclusively be tied to the published answers. Historical corpus equivalence between systems is therefore unverified. Original execution IDs, complete preprocessing records, and exact download provenance are unavailable in the inspected material.

## Attribution and licensing scope

The project's software license does not relicense source editions, translations, editorial material, or third-party software. Refer to the source editions and their accompanying notices for applicable terms, and retain those notices when distributing source material.

Rousseau and the translators are credited for their texts, not as authors of this project's software. Generated answers and graph reports are project outputs and should not be presented as verbatim Rousseau passages without source verification.

Use the repository's `CITATION.cff` to cite the software project and cite the relevant source edition separately when discussing or quoting Rousseau.
