"""
index.py — Sprint 1–4: Build RAG Index
=======================================
Mục tiêu:
  - Đọc và preprocess tài liệu từ data/docs/
  - Chunk tài liệu theo cấu trúc tự nhiên (heading/section)
  - Gắn metadata: source, section, department, effective_date, access
  - Embed bằng OpenAI text-embedding-3-small và lưu vào ChromaDB

Definition of Done:
  ✓ Script chạy được và index đủ docs
  ✓ Mỗi section = 1 chunk (không cắt vụn tài liệu nhỏ)
  ✓ Chunk rác (tiêu đề ≤ MIN_CHUNK_CHARS) bị lọc bỏ
  ✓ Metadata đầy đủ: source, section, effective_date, department
  ✓ 0 duplicates
  ✓ diagnostics_report() báo Overall ✅
"""

import os
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv
from day08.lab.src.core.data_ingestor import (
    extract_metadata,
    remove_metadata_lines,
    extract_heading,
    clean_text,
)

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from vector_store_manager import get_chroma_collection

_OPENAI_CLIENT: Optional["OpenAI"] = None

# =============================================================================
# CẤU HÌNH
# =============================================================================
BASE_DIR = Path(__file__).resolve().parents[2]

DOCS_DIR = BASE_DIR / "data" / "docs"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
print(DOCS_DIR)
# TODO Sprint 1: Điều chỉnh chunk size và overlap theo quyết định của nhóm
# Gợi ý từ slide: chunk 300-500 tokens, overlap 50-80 tokens
CHUNK_SIZE = 400       # tokens (ước lượng bằng số ký tự / 4)
CHUNK_OVERLAP = 80     # tokens overlap giữa các chunk


# =============================================================================
# STEP 1: PREPROCESS
# =============================================================================

def preprocess_document(raw_text: str, filepath: str) -> Dict[str, Any]:
    """
    Preprocess một tài liệu: extract metadata từ header và làm sạch nội dung.

    Returns:
        {
          "text":     nội dung đã clean,
          "metadata": {source, department, effective_date, access, alias, heading}
        }
    """
    metadata     = extract_metadata(raw_text, filepath)
    content      = remove_metadata_lines(raw_text)
    heading      = extract_heading(content)
    metadata["heading"] = heading
    cleaned_text = clean_text(content)
    doc = {
        "text": cleaned_text,
        "metadata": metadata,
    }

    out_dir = save_processed_doc(doc)
    print(out_dir)

    return doc

# =============================================================================
# STEP 2: CHUNK
# =============================================================================

def chunk_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk tài liệu đã preprocess theo heading → paragraph → sentence.

    Pipeline:
      1. Split theo heading "=== ... ===" → các section.
      2. Mỗi section nếu dài hơn chunk_chars thì split theo paragraph.
      3. Paragraph quá dài tiếp tục split theo câu.
      4. Thêm overlap: phần đuôi chunk trước làm đầu chunk tiếp theo.
      5. Lọc bỏ chunk ngắn hơn MIN_CHUNK_CHARS (tiêu đề thuần tuý).
    """
    text          = doc["text"]
    base_metadata = doc["metadata"].copy()

    raw_chunks: List[Dict[str, Any]] = []

    # Bước 1: split theo section heading "=== ... ==="
    sections = re.split(r"(===.*?===)", text)
    current_section      = "General"
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
            current_section      = part.strip("= ").strip()
            current_section_text = ""
        else:
            current_section_text += part

    # Section cuối
    if current_section_text.strip():
        raw_chunks.extend(
            _split_by_size(
                current_section_text.strip(),
                base_metadata=base_metadata,
                section=current_section,
            )
        )

    # Bước 5: lọc chunk rác (tiêu đề thuần tuý, quá ngắn)
    chunks = [c for c in raw_chunks if len(c["text"].strip()) >= MIN_CHUNK_CHARS]

    return chunks


def _split_by_size(
    text: str,
    base_metadata: Dict,
    section: str,
    chunk_chars: int   = CHUNK_SIZE * 4,
    overlap_chars: int = CHUNK_OVERLAP * 4,
) -> List[Dict[str, Any]]:
    """
    Split một section thành các chunk tự nhiên (paragraph + overlap).

    Nếu toàn bộ section vừa trong một chunk → trả về ngay (1 chunk = 1 section).
    Nếu không → gom paragraph cho đến đầy, chunk tiếp theo bắt đầu bằng
    overlap_buffer lấy từ đuôi chunk trước.
    """
    text = text.strip()

    # Vừa 1 chunk → trả về ngay, không cắt
    if len(text) <= chunk_chars:
        return [{"text": text, "metadata": {**base_metadata, "section": section}}]

    # Normalize thành danh sách paragraph / sub-paragraph
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

    # Gom paragraph thành chunk, thêm overlap
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
            "text":     chunk_text,
            "metadata": {**base_metadata, "section": section},
        })

        overlap_buffer = (
            _extract_overlap_tail(chunk_text, overlap_chars)
            if cursor < len(paragraphs)
            else ""
        )

    return chunks


def _split_long_paragraph(paragraph: str, chunk_chars: int) -> List[str]:
    """Chia paragraph dài theo ranh giới câu."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    segments: List[str] = []
    builder: List[str]  = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sep       = 1 if builder else 0
        candidate = current_len + sep + len(sentence)

        if builder and candidate > chunk_chars:
            segments.append(" ".join(builder))
            builder     = [sentence]
            current_len = len(sentence)
        else:
            builder.append(sentence)
            current_len = candidate

    if builder:
        segments.append(" ".join(builder))

    return segments or [paragraph[:chunk_chars]]


def _extract_overlap_tail(text: str, overlap_chars: int) -> str:
    """Lấy phần đuôi của chunk làm overlap cho chunk tiếp theo."""
    if overlap_chars <= 0 or not text:
        return ""
    return text[-overlap_chars:].lstrip()


# =============================================================================
# STEP 3: EMBED + STORE
# =============================================================================

def _get_openai_client() -> "OpenAI":
    global _OPENAI_CLIENT
    if OpenAI is None:
        raise RuntimeError("Package `openai` chưa cài. Chạy `pip install openai`.")
    if _OPENAI_CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Không tìm thấy `OPENAI_API_KEY` trong .env.")
        _OPENAI_CLIENT = OpenAI(api_key=api_key)
    return _OPENAI_CLIENT


def get_embedding(text: str) -> List[float]:
    """Tạo embedding vector bằng OpenAI text-embedding-3-small."""
    client   = _get_openai_client()
    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding


def build_index(docs_dir: Path = DOCS_DIR, db_dir: Path = CHROMA_DB_DIR) -> None:
    """
    Pipeline hoàn chỉnh:
      đọc docs → preprocess → chunk → filter → embed → upsert vào ChromaDB.
    """
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
        doc      = preprocess_document(raw_text, str(filepath))
        chunks   = chunk_document(doc)

        for i, chunk in enumerate(chunks):
            chunk_id  = f"{filepath.stem}_{i}"
            embedding = get_embedding(chunk["text"])
            collection.upsert(
                ids        = [chunk_id],
                embeddings = [embedding],
                documents  = [chunk["text"]],
                metadatas  = [chunk["metadata"]],
            )

        total_chunks += len(chunks)
        print(f"    → {len(chunks)} chunks indexed")

    print(f"\nHoàn thành! Tổng số chunks: {total_chunks}")


# =============================================================================
# STEP 4: INSPECT / DIAGNOSTICS
# =============================================================================

def list_chunks(db_dir: Path = CHROMA_DB_DIR, n: int = 5) -> None:
    """In ra n chunk đầu tiên để kiểm tra chất lượng index."""
    try:
        import chromadb
        client     = chromadb.PersistentClient(path=str(db_dir))
        collection = client.get_collection("rag_lab")
        results    = collection.get(limit=n, include=["documents", "metadatas"])

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
    """Kiểm tra phân phối metadata trong toàn bộ index."""
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
    missing     = Counter()

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
        count  = missing[field]
        status = "✓" if count == 0 else f"⚠ {count} chunks thiếu"
        print(f"  {field}: {status}")


def diagnostics_report(
    db_dir: Path = CHROMA_DB_DIR,
    sample_short: int = 3,
    sample_long:  int = 3,
) -> None:
    """
    Sprint 4 – Error Tree diagnostics.

    Nhánh 1 — Chunk có đúng không?
      • Avg length >= 40% max_len (không cắt vụn section)
      • Min length >= MIN_CHUNK_CHARS (không có chunk rác)

    Nhánh 2 — Metadata có đủ không?
      • source, section, effective_date: 0 chunks thiếu

    Nhánh 3 — Trùng lặp?
      • 0 duplicate chunk texts
    """
    try:
        collection = get_chroma_collection(db_dir)
    except RuntimeError as exc:
        print(f"Lỗi khi khởi tạo Chroma: {exc}")
        return

    records = _collect_index_records(collection)
    if not records:
        print("Chưa có index. Chạy build_index() trước.")
        return

    # --- Thu thập số liệu ---
    lengths    = [(len(text), text, meta) for text, meta in records]
    avg_len    = sum(l for l, *_ in lengths) / len(lengths)
    min_len    = min(l for l, *_ in lengths)
    max_len    = max(l for l, *_ in lengths)

    sections   = Counter()
    seen_texts = Counter()
    missing    = Counter()

    for text, meta in records:
        sections[meta.get("section", "unknown")] += 1
        seen_texts[text.strip()] += 1
        for field in ("source", "section", "effective_date"):
            if not meta.get(field):
                missing[field] += 1

    duplicates = {t for t, freq in seen_texts.items() if freq > 1}

    # --- Đánh giá chất lượng ---
    # avg >= 40% max_len: đảm bảo không cắt vụn section
    # (dùng max_len thực tế vì corpus nhỏ, không dùng chunk_chars cứng)
    dynamic_target = max_len * 0.4
    chunk_ok   = avg_len >= dynamic_target
    meta_ok    = all(v == 0 for v in missing.values())
    dup_ok     = len(duplicates) == 0

    # --- In report ---
    print("\n" + "=" * 60)
    print("Diagnostics Report — Sprint 4 Error Tree")
    print("=" * 60)

    print(f"\n[Nhánh 1] Chunk quality")
    print(f"    Total chunks   : {len(records)}")
    print(f"    Avg length     : {avg_len:.0f} chars")
    print(f"    Min / Max      : {min_len} / {max_len} chars")
    print(f"    MIN_CHUNK_CHARS: {MIN_CHUNK_CHARS} chars  (ngưỡng lọc chunk rác)")
    print(f"    Dynamic target : avg >= {dynamic_target:.0f} chars  (40% x max={max_len})")
    if chunk_ok:
        print(f"    Status         : OK -- chunk giu nguyen section, khong cat vun")
    else:
        print(f"    Status         : !! avg qua thap -- chunking dang cat vun section")

    print(f"\n[Nhánh 2] Metadata coverage")
    for field in ("source", "section", "effective_date"):
        count  = missing[field]
        status = "OK" if count == 0 else f"!! {count} chunks thieu"
        print(f"    {field:<20}: {status}")
    print(f"    Overall        : {'OK' if meta_ok else '!! Co truong metadata bi thieu'}")

    print(f"\n[Nhánh 3] Duplicates")
    dup_status = "OK" if dup_ok else f"!! {len(duplicates)} duplicates -- can dedup"
    print(f"    Duplicate chunks: {len(duplicates)}  {dup_status}")

    print(f"\n[Nhánh 4] Section distribution (top 10)")
    for section, count in sections.most_common(10):
        bar = "=" * count
        print(f"    {section[:45]:<45} {count:>3}  {bar}")

    def _print_samples(label: str, entries: list):
        print(f"\n[Sample] {label} (showing {len(entries)}):")
        for idx, (length, text, meta) in enumerate(entries, 1):
            preview = text[:100].replace("\n", " ")
            sec     = meta.get("section", "N/A")
            print(f"    {idx}. section={sec!r:<35} len={length:>4} | {preview}")

    sorted_lengths = sorted(lengths, key=lambda x: x[0])
    _print_samples("Shortest chunks", sorted_lengths[:sample_short])
    _print_samples("Longest chunks",  sorted_lengths[-sample_long:])

    # --- Tổng kết ---
    all_ok = chunk_ok and meta_ok and dup_ok
    print("\n" + "-" * 60)
    if all_ok:
        print("Overall: [OK] Index sach -- san sang cho retrieval")
    else:
        print("Overall: [!!] Can xem lai cac nhanh duoc danh dau tren")
    print("=" * 60)


# =============================================================================
# MAIN — smoke test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 1-4: Build RAG Index")
    print("=" * 60)

    doc_files = list(DOCS_DIR.glob("*.txt"))
    print(f"\nTim thay {len(doc_files)} tai lieu:")
    for f in doc_files:
        print(f"  - {f.name}")

    print("\n--- Test preprocess + chunking (khong can API key) ---")
    for filepath in doc_files[:1]:
        raw    = filepath.read_text(encoding="utf-8")
        doc    = preprocess_document(raw, str(filepath))
        chunks = chunk_document(doc)
        print(f"\nFile: {filepath.name}")
        print(f"  Metadata : {doc['metadata']}")
        print(f"  So chunks: {len(chunks)}")
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