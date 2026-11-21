# database.py

from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

CHROMA_PATH = PROJECT_DIR / "chroma_db"
COLLECTION_NAME = "rousseau_collection"


def get_embedding_function():
    """
    Creates the embedding model.
    This turns text into vectors.
    """
    return OpenAIEmbeddings(model="text-embedding-3-large")


def get_vector_store():
    """
    Opens the Chroma vector database.
    If chroma_db/ does not exist yet, Chroma can create it.
    """
    embedding_function = get_embedding_function()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_PATH),
        embedding_function=embedding_function
    )

    return vector_store
