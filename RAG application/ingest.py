"""Build Chroma from the same prepared input files consumed by GraphRAG."""
import argparse
import os
import shutil
import sys

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from database import CHROMA_PATH, PROJECT_DIR, get_vector_store

sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from prepare_data import verify

DATA_FOLDER = PROJECT_DIR / "input"


def load_text_files():
    manifest = verify(PROJECT_DIR)
    return [Document(page_content=(DATA_FOLDER / row["filename"]).read_text(encoding="utf-8"),
                     metadata={"source": row["filename"], "source_sha256": row["prepared_sha256"],
                               "corpus_id": manifest["corpus_id"]})
            for row in manifest["files"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace the existing project Chroma database")
    parser.add_argument("--dry-run", action="store_true", help="Validate and split without APIs or database writes")
    args = parser.parse_args()
    documents = load_text_files()
    chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100).split_documents(documents)
    if not chunks:
        raise ValueError("No chunks were produced")
    print(f"Prepared {len(documents)} documents and {len(chunks)} chunks")
    if args.dry_run:
        return
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("Set OPENAI_API_KEY in the project .env before ingestion")
    if CHROMA_PATH.exists():
        if not args.reset:
            raise FileExistsError("Chroma already exists. Use --reset to explicitly rebuild it.")
        if CHROMA_PATH.is_symlink() or CHROMA_PATH.resolve() != PROJECT_DIR.resolve() / "chroma_db":
            raise ValueError("Refusing to remove an unexpected database path")
        shutil.rmtree(CHROMA_PATH)
    store = get_vector_store()
    for start in range(0, len(chunks), 64):
        batch = chunks[start:start + 64]
        store.add_documents(batch, ids=[f"chunk_{i}" for i in range(start, start + len(batch))])
        print(f"Stored {start + len(batch)}/{len(chunks)} chunks")


if __name__ == "__main__":
    main()
