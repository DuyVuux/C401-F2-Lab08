import json
import logging
from pathlib import Path
from typing import Dict, Any, List

import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CLEANED_INPUT = Path(__file__).parent.parent / "artifacts" / "cleaned_records.jsonl"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
COLLECTION = "day10_docs"

def chunk_record(record: Dict[str, Any], max_length: int = 1000) -> List[Dict[str, Any]]:
    content = record.get("content", "")
    if not content:
        content = json.dumps(record, ensure_ascii=False)
        
    doc_id = record.get("doc_id", "")
    effective_date = record.get("effective_date", "")
    source = record.get("source", "")
    
    chunks = [content[i:i + max_length] for i in range(0, len(content), max_length)] if content else [""]
    
    return [
        {
            "chunk_id": f"{doc_id}_{idx}" if doc_id else f"unknown_{idx}",
            "text": chunk,
            "metadata": {
                "effective_date": str(effective_date) if effective_date else "",
                "source": str(source) if source else "",
                "doc_id": str(doc_id) if doc_id else ""
            }
        }
        for idx, chunk in enumerate(chunks)
    ]

def embed_and_upsert(run_id: str = "") -> None:
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collection = client.get_or_create_collection(name=COLLECTION)
        openai_client = OpenAI()
    except Exception as e:
        logger.error(f"Initialization fallback: {e}")
        return
        
    chunks_to_upsert = []
    
    if CLEANED_INPUT.exists():
        with open(CLEANED_INPUT, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        chunks_to_upsert.extend(chunk_record(record))
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON schema error: {e}")
                    
    if not chunks_to_upsert:
        return

    texts = [c["text"] for c in chunks_to_upsert]
    ids = [c["chunk_id"] for c in chunks_to_upsert]
    
    metadatas = []
    for c in chunks_to_upsert:
        meta = dict(c["metadata"])
        meta["run_id"] = run_id
        metadatas.append(meta)

    embeddings = []
    valid_indices = []
    
    for idx, text in enumerate(texts):
        try:
            response = openai_client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            embeddings.append(response.data[0].embedding)
            valid_indices.append(idx)
        except Exception as e:
            logger.error(f"OpenAI fallback for {ids[idx]}: {e}")

    if embeddings:
        final_ids = [ids[i] for i in valid_indices]
        final_texts = [texts[i] for i in valid_indices]
        final_metas = [metadatas[i] for i in valid_indices]
        
        try:
            collection.upsert(
                ids=final_ids,
                embeddings=embeddings,
                metadatas=final_metas,
                documents=final_texts
            )
        except Exception as e:
            logger.error(f"Chroma DB upsert error: {e}")

if __name__ == "__main__":
    embed_and_upsert(run_id="manual_run")
