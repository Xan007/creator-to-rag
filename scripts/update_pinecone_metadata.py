import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import get_session
import storage.repositories as repo
from src.indexer.pinecone_indexer import PineconeIndexer

def update_metadata():
    db = get_session()
    try:
        indexer = PineconeIndexer()
        index = indexer.index
        chunks = db.query(repo.Chunk).all()
        print(f"Found {len(chunks)} chunks. Updating metadata...", flush=True)
        
        updates = 0
        from concurrent.futures import ThreadPoolExecutor
        
        def update_chunk(chunk):
            if not chunk.library_id:
                return False
            vector_id = f"source:{chunk.library_id}:{chunk.source_id}:{chunk.ordinal}"
            try:
                index.update(id=vector_id, set_metadata={"library_id": chunk.library_id})
                return True
            except Exception as e:
                # If the vector doesn't exist or other error, return False
                return False

        with ThreadPoolExecutor(max_workers=20) as executor:
            results = executor.map(update_chunk, chunks)
            updates = sum(1 for r in results if r)
                
        print(f"Done updating metadata for {updates} chunks. RAG should work now!", flush=True)
    finally:
        db.close()

if __name__ == "__main__":
    update_metadata()
