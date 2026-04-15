"""
embed_pipeline.py — Sprint 2a (Vũ Đức Duy)
Module embed độc lập dùng OpenAI text-embedding-3-small (thay vì SentenceTransformer của baseline).

Đọc cleaned CSV từ artifacts/cleaned/ (output của etl_pipeline.py run),
upsert vào collection day10_kb (cùng collection với etl_pipeline.py để grading_run.py
và eval_retrieval.py tìm thấy data).

Idempotent: upsert theo chunk_id + prune id cũ không còn trong cleaned CSV.

Chạy:
    python transform/embed_pipeline.py
    python transform/embed_pipeline.py --run-id sprint2a --cleaned artifacts/cleaned/cleaned_<run_id>.csv
"""

import argparse
import csv
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CHROMA_PATH = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
COLLECTION = os.environ.get("CHROMA_COLLECTION", "day10_kb")
EMBEDDING_MODEL = "text-embedding-3-small"


def _latest_cleaned_csv() -> Path | None:
    """Tìm file cleaned CSV mới nhất trong artifacts/cleaned/."""
    clean_dir = ROOT / "artifacts" / "cleaned"
    csvs = sorted(
        [f for f in clean_dir.glob("cleaned_*.csv") if "smoke" not in f.name],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return csvs[0] if csvs else None


def load_cleaned_csv(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def embed_and_upsert(cleaned_csv: Path | None = None, run_id: str = "embed_pipeline") -> dict:
    import chromadb
    from openai import OpenAI

    # Resolve cleaned CSV
    if cleaned_csv is None:
        cleaned_csv = _latest_cleaned_csv()
    if cleaned_csv is None or not cleaned_csv.is_file():
        logger.error("Không tìm thấy cleaned CSV. Chạy etl_pipeline.py run trước.")
        return {}

    rows = load_cleaned_csv(cleaned_csv)
    if not rows:
        logger.warning("Cleaned CSV rỗng — không embed.")
        return {}

    logger.info(f"cleaned_csv={cleaned_csv.name} rows={len(rows)}")

    # Init ChromaDB + collection (cùng collection với etl_pipeline.py)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(name=COLLECTION)

    # Prune: xóa chunk_id không còn trong cleaned CSV (idempotency)
    current_ids = [r["chunk_id"] for r in rows]
    try:
        prev = col.get(include=[])
        prev_ids = set(prev.get("ids") or [])
        drop = sorted(prev_ids - set(current_ids))
        if drop:
            col.delete(ids=drop)
            logger.info(f"embed_prune_removed={len(drop)}")
    except Exception as e:
        logger.warning(f"Prune skip: {e}")

    # Embed từng row với OpenAI
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    ids, documents, metadatas, embeddings = [], [], [], []

    for r in rows:
        chunk_id = r.get("chunk_id", "")
        text = r.get("chunk_text", "")
        if not chunk_id or not text:
            continue
        try:
            resp = openai_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
            ids.append(chunk_id)
            documents.append(text)
            metadatas.append({
                "doc_id": r.get("doc_id", ""),
                "effective_date": r.get("effective_date", ""),
                "run_id": run_id,
            })
            embeddings.append(resp.data[0].embedding)
        except Exception as e:
            logger.error(f"Embed failed for {chunk_id}: {e}")

    if not ids:
        logger.error("Không có chunk nào được embed thành công.")
        return {}

    col.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    result = {
        "run_id": run_id,
        "cleaned_csv": str(cleaned_csv.name),
        "chunks_upserted": len(ids),
        "collection": COLLECTION,
    }
    logger.info(f"embed_upsert count={len(ids)} collection={COLLECTION}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed cleaned CSV → ChromaDB (OpenAI)")
    parser.add_argument("--cleaned", default=None, help="Path tới cleaned CSV (mặc định: tìm file mới nhất)")
    parser.add_argument("--run-id", default="embed_pipeline", help="Run ID để ghi vào metadata")
    args = parser.parse_args()

    cleaned = Path(args.cleaned) if args.cleaned else None
    result = embed_and_upsert(cleaned_csv=cleaned, run_id=args.run_id)
    if result:
        print(result)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
