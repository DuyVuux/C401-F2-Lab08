import os
import re
import json
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv
from src.core.data_ingestor import (
    extract_metadata,
    remove_metadata_lines,
    extract_heading,
    clean_text,
    save_processed_doc,
)
from vector_store_manager import get_chroma_collection

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

_OPENAI_CLIENT: Optional["OpenAI"] = None

BASE_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BASE_DIR / "data" / "docs"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"

CHUNK_SIZE = 700
CHUNK_OVERLAP = 20
MIN_CHUNK_CHARS = 80


def preprocess_document(raw_text: str, filepath: str) -> Dict[str, Any]:
    metadata = extract_metadata(raw_text, filepath)
    content = remove_metadata_lines(raw_text)
    heading = extract_heading(content)
    metadata["heading"] = heading
    cleaned_text = clean_text(content)
    return {"text": cleaned_text, "metadata": metadata}


def chunk_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = doc["text"]
    base_metadata = doc["metadata"].copy()
    raw_chunks: List[Dict[str, Any]] = []

    sections = re.split(r"(===.*?===)", text)
    current_section = "General"
    current_section_text = ""

    for part in sections:
        if re.match(r"===.*?===", part):
            if current_section_text.strip():
                raw_chunks.extend(
                    _split_by_size(
                        current_section_text.strip(),
                        base_metadata=base_metadata,
                        section=current_section,
                    )
                )
            current_section = part.strip("= ").strip()
            current_section_text = ""
        else:
            current_section_text += part

    if current_section_text.strip():
        raw_chunks.extend(
            _split_by_size(
                current_section_text.strip(),
                base_metadata=base_metadata,
                section=current_section,
            )
        )

    return [c for c in raw_chunks if len(c["text"].strip()) >= MIN_CHUNK_CHARS]


def _split_by_size(
    text: str,
    base_metadata: Dict,
    section: str,
    chunk_chars: int = CHUNK_SIZE * 4,
    overlap_chars: int = CHUNK_OVERLAP * 4,
) -> List[Dict[str, Any]]:
    text = text.strip()

    if len(text) <= chunk_chars:
        return [{"text": text, "metadata": {**base_metadata, "section": section}}]

    paragraphs: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) > chunk_chars:
            paragraphs.extend(_split_long_paragraph(para, chunk_chars))
        else:
            paragraphs.append(para)

    if not paragraphs:
        paragraphs = [text]

    chunks: List[Dict[str, Any]] = []
    overlap_buffer = ""
    cursor = 0

    while cursor < len(paragraphs):
        chunk_parts: List[str] = []
        current_len = 0

        if overlap_buffer:
            chunk_parts.append(overlap_buffer)
            current_len = len(overlap_buffer)

        while cursor < len(paragraphs):
            paragraph = paragraphs[cursor]
            delimiter = 2 if chunk_parts else 0
            candidate = current_len + delimiter + len(paragraph)

            if chunk_parts and candidate > chunk_chars:
                break

            current_len += delimiter + len(paragraph)
            chunk_parts.append(paragraph)
            cursor += 1

        chunk_text = "\n\n".join(chunk_parts).strip()
        if not chunk_text:
            continue

        chunks.append({
            "text": chunk_text,
            "metadata": {**base_metadata, "section": section},
        })

        overlap_buffer = (
            _extract_overlap_tail(chunk_text, overlap_chars)
            if cursor < len(paragraphs)
            else ""
        )

    return chunks


def _split_long_paragraph(paragraph: str, chunk_chars: int) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    segments: List[str] = []
    builder: List[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sep = 1 if builder else 0
        candidate = current_len + sep + len(sentence)

        if builder and candidate > chunk_chars:
            segments.append(" ".join(builder))
            builder = [sentence]
            current_len = len(sentence)
        else:
            builder.append(sentence)
            current_len = candidate

    if builder:
        segments.append(" ".join(builder))

    return segments or [paragraph[:chunk_chars]]


def _extract_overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or not text:
        return ""
    return text[-overlap_chars:].lstrip()


def _get_openai_client() -> "OpenAI":
    global _OPENAI_CLIENT
    if OpenAI is None:
        raise RuntimeError("Package `openai` chưa cài. Chạy: uv pip install openai")
    if _OPENAI_CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Không tìm thấy OPENAI_API_KEY trong .env")
        _OPENAI_CLIENT = OpenAI(api_key=api_key)
    return _OPENAI_CLIENT


def get_embedding(text: str) -> List[float]:
    client = _get_openai_client()
    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding


def build_index(docs_dir: Path = DOCS_DIR, db_dir: Path = CHROMA_DB_DIR) -> None:
    print(f"Đang build index từ: {docs_dir}")
    db_dir.mkdir(parents=True, exist_ok=True)
    collection = get_chroma_collection(db_dir)

    doc_files = list(docs_dir.glob("*.txt"))
    if not doc_files:
        print(f"Không tìm thấy file .txt trong {docs_dir}")
        return

    total_chunks = 0
    for filepath in doc_files:
        print(f"  Processing: {filepath.name}")
        raw_text = filepath.read_text(encoding="utf-8")

        doc = preprocess_document(raw_text, str(filepath))
        doc["metadata"].setdefault("source", str(filepath))
        doc["metadata"].setdefault("department", "unknown")
        doc["metadata"].setdefault("effective_date", "unknown")

        chunks = chunk_document(doc)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{filepath.stem}_{i}"
            embedding = get_embedding(chunk["text"])
            collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk["text"]],
                metadatas=[chunk["metadata"]],
            )

        total_chunks += len(chunks)
        print(f"    -> {len(chunks)} chunks indexed")

    print(f"\nHoàn thành! Tổng số chunks: {total_chunks}")


def list_chunks(db_dir: Path = CHROMA_DB_DIR, n: int = 5) -> None:
    try:
        collection = get_chroma_collection(db_dir)
        results = collection.get(limit=n, include=["documents", "metadatas"])

        print(f"\n=== Top {n} chunks trong index ===\n")
        for i, (doc, meta) in enumerate(
            zip(results["documents"], results["metadatas"])
        ):
            print(f"[Chunk {i+1}]")
            print(f"  Source:         {meta.get('source', 'N/A')}")
            print(f"  Section:        {meta.get('section', 'N/A')}")
            print(f"  Department:     {meta.get('department', 'N/A')}")
            print(f"  Effective Date: {meta.get('effective_date', 'N/A')}")
            print(f"  Length:         {len(doc)} chars")
            print(f"  Text preview:   {doc[:150]}...")
            print()
    except Exception as e:
        print(f"Lỗi khi đọc index: {e}")
        print("Hãy chạy build_index() trước.")


def _collect_index_records(
    collection,
) -> List[Tuple[str, Dict[str, Any]]]:
    results = collection.get(include=["documents", "metadatas"])
    return list(zip(results.get("documents", []), results.get("metadatas", [])))


def inspect_metadata_coverage(db_dir: Path = CHROMA_DB_DIR) -> None:
    try:
        collection = get_chroma_collection(db_dir)
    except RuntimeError as exc:
        print(f"Lỗi khi khởi tạo Chroma: {exc}")
        return

    records = _collect_index_records(collection)
    if not records:
        print("Chưa có index. Chạy build_index() trước.")
        return

    departments = Counter()
    missing = Counter()

    for _, meta in records:
        departments[meta.get("department", "unknown")] += 1
        for field in ("source", "section", "effective_date"):
            if not meta.get(field):
                missing[field] += 1

    print(f"\nTổng chunks: {len(records)}")
    print("Phân bố theo department:")
    for dept, count in departments.most_common():
        print(f"  {dept}: {count} chunks")
    print("Chunks thiếu metadata:")
    for field in ("source", "section", "effective_date"):
        count = missing[field]
        status = "OK" if count == 0 else f"!! {count} chunks thiếu"
        print(f"  {field}: {status}")


def diagnostics_report(
    db_dir: Path = CHROMA_DB_DIR,
    sample_short: int = 3,
    sample_long: int = 3,
) -> None:
    try:
        collection = get_chroma_collection(db_dir)
    except RuntimeError as exc:
        print(f"Lỗi khi khởi tạo Chroma: {exc}")
        return

    records = _collect_index_records(collection)
    if not records:
        print("Chưa có index. Chạy build_index() trước.")
        return

    lengths = [(len(text), text, meta) for text, meta in records]
    avg_len = sum(l for l, *_ in lengths) / len(lengths)
    min_len = min(l for l, *_ in lengths)
    max_len = max(l for l, *_ in lengths)

    sections = Counter()
    seen_texts = Counter()
    missing = Counter()

    for text, meta in records:
        sections[meta.get("section", "unknown")] += 1
        seen_texts[text.strip()] += 1
        for field in ("source", "section", "effective_date"):
            if not meta.get(field):
                missing[field] += 1

    duplicates = {t for t, freq in seen_texts.items() if freq > 1}

    dynamic_target = max_len * 0.4
    chunk_ok = avg_len >= dynamic_target
    meta_ok = all(v == 0 for v in missing.values())
    dup_ok = len(duplicates) == 0

    print("\n" + "=" * 60)
    print("Diagnostics Report — Sprint 4 Error Tree")
    print("=" * 60)

    print(f"\n[Nhánh 1] Chunk quality")
    print(f"    Total chunks   : {len(records)}")
    print(f"    Avg length     : {avg_len:.0f} chars")
    print(f"    Min / Max      : {min_len} / {max_len} chars")
    print(f"    MIN_CHUNK_CHARS: {MIN_CHUNK_CHARS} chars")
    print(f"    Dynamic target : avg >= {dynamic_target:.0f} chars (40% x max={max_len})")
    if chunk_ok:
        print(f"    Status         : OK -- chunk giữ nguyên section, không cắt vụn")
    else:
        print(f"    Status         : !! avg quá thấp -- chunking đang cắt vụn section")

    print(f"\n[Nhánh 2] Metadata coverage")
    for field in ("source", "section", "effective_date"):
        count = missing[field]
        status = "OK" if count == 0 else f"!! {count} chunks thiếu"
        print(f"    {field:<20}: {status}")
    print(f"    Overall        : {'OK' if meta_ok else '!! Có trường metadata bị thiếu'}")

    print(f"\n[Nhánh 3] Duplicates")
    dup_status = "OK" if dup_ok else f"!! {len(duplicates)} duplicates -- cần dedup"
    print(f"    Duplicate chunks: {len(duplicates)}  {dup_status}")

    print(f"\n[Nhánh 4] Section distribution (top 10)")
    for section, count in sections.most_common(10):
        bar = "=" * count
        print(f"    {section[:45]:<45} {count:>3}  {bar}")

    def _print_samples(label: str, entries: list):
        print(f"\n[Sample] {label} (showing {len(entries)}):")
        for idx, (length, text, meta) in enumerate(entries, 1):
            preview = text[:100].replace("\n", " ")
            sec = meta.get("section", "N/A")
            print(f"    {idx}. section={sec!r:<35} len={length:>4} | {preview}")

    sorted_lengths = sorted(lengths, key=lambda x: x[0])
    _print_samples("Shortest chunks", sorted_lengths[:sample_short])
    _print_samples("Longest chunks", sorted_lengths[-sample_long:])

    all_ok = chunk_ok and meta_ok and dup_ok
    print("\n" + "-" * 60)
    if all_ok:
        print("Overall: [OK] Index sạch -- sẵn sàng cho retrieval")
    else:
        print("Overall: [!!] Cần xem lại các nhánh được đánh dấu trên")
    print("=" * 60)


def evaluate_retrieval(json_path: Path, top_k: int = 3):
    collection = get_chroma_collection(CHROMA_DB_DIR)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data)
    hit = 0

    for item in data:
        question = item["question"]
        expected_sources = set(item.get("expected_sources", []))

        embedding = get_embedding(question)

        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
        )

        retrieved_sources = set()
        for meta in results["metadatas"][0]:
            if meta and "source" in meta:
                retrieved_sources.add(meta["source"])

        ok = len(expected_sources & retrieved_sources) > 0 if expected_sources else True

        if ok:
            hit += 1

        print("\n" + "=" * 60)
        print(f"Q: {question}")
        print(f"Expected: {expected_sources}")
        print(f"Retrieved: {retrieved_sources}")
        print(f"Result: {'HIT' if ok else 'MISS'}")

    print("\n" + "=" * 60)
    print(f"FINAL SCORE: {hit}/{total} = {hit/total:.2%}")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 1-4: Build RAG Index")
    print("=" * 60)

    doc_files = list(DOCS_DIR.glob("*.txt"))
    print(f"\nTìm thấy {len(doc_files)} tài liệu:")
    for f in doc_files:
        print(f"  - {f.name}")

    print("\n--- Test preprocess + chunking ---")
    for filepath in doc_files[:1]:
        raw = filepath.read_text(encoding="utf-8")
        doc = preprocess_document(raw, str(filepath))
        chunks = chunk_document(doc)
        print(f"\nFile: {filepath.name}")
        print(f"  Metadata : {doc['metadata']}")
        print(f"  Số chunks: {len(chunks)}")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n  [Chunk {i+1}] Section : {chunk['metadata']['section']}")
            print(f"              Length  : {len(chunk['text'])} chars")
            print(f"              Preview : {chunk['text'][:150]}...")

    print("\n--- Build Full Index ---")
    build_index()

    print("\n--- list_chunks() ---")
    list_chunks()

    print("\n--- inspect_metadata_coverage() ---")
    inspect_metadata_coverage()

    print("\n--- diagnostics_report() ---")
    diagnostics_report()
