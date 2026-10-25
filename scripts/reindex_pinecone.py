import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import get_session
import storage.repositories as repo
from src.indexer.pinecone_indexer import PineconeIndexer

def reindex_all():
    db = get_session()
    try:
        indexer = PineconeIndexer()
        posts = db.query(repo.Post).all()
        print(f"Found {len(posts)} posts to re-index.")
        for post in posts:
            if not post.extracted_knowledge:
                continue
            print(f"Re-indexing post {post.id} (library {post.library_id})...")
            while True:
                try:
                    indexer.index_source(
                        source_id=post.id,
                        library_id=post.library_id,
                        url=post.url,
                        platform="unknown",
                        author=post.creator_username,
                        title="",
                        description=post.description,
                        extracted_text=post.extracted_knowledge,
                        ingest_status="reindexed"
                    )
                    break
                except RuntimeError as e:
                    if "quota exhausted" in str(e):
                        import time
                        print("Quota exhausted, sleeping 60 seconds...")
                        time.sleep(60)
                    else:
                        raise
        print("Done re-indexing.")
    finally:
        db.close()

if __name__ == "__main__":
    reindex_all()

