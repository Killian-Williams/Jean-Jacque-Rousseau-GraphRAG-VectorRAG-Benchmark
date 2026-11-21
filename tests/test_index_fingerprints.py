from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment import chroma_content_hash


class ChromaFingerprintTests(unittest.TestCase):
    def test_lock_changes_do_not_hide_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with closing(sqlite3.connect(root/'chroma.sqlite3')) as db:
                db.executescript('CREATE TABLE acquire_write(id INTEGER, lock INTEGER);'
                                 'CREATE TABLE embeddings(id INTEGER, document TEXT);'
                                 "INSERT INTO embeddings VALUES(1, 'original');")
                db.commit()
            (root/'vectors.bin').write_bytes(b'original-vectors')
            original = chroma_content_hash(root)
            with closing(sqlite3.connect(root/'chroma.sqlite3')) as db:
                db.execute('INSERT INTO acquire_write VALUES(1,1)')
                db.commit()
            self.assertEqual(original, chroma_content_hash(root))
            with closing(sqlite3.connect(root/'chroma.sqlite3')) as db:
                db.execute("UPDATE embeddings SET document='changed'")
                db.commit()
            self.assertNotEqual(original, chroma_content_hash(root))

    def test_vector_bytes_are_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with closing(sqlite3.connect(root/'chroma.sqlite3')) as db:
                db.execute('CREATE TABLE embeddings(id INTEGER)')
                db.commit()
            (root/'vectors.bin').write_bytes(b'original-vectors')
            original = chroma_content_hash(root)
            (root/'vectors.bin').write_bytes(b'changed-vectors')
            self.assertNotEqual(original, chroma_content_hash(root))
