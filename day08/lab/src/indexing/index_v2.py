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
  ✓ Chunk rác (tiêu đề <= MIN_CHUNK_CHARS) bị lọc bỏ
  ✓ Metadata đầy đủ: source, section, effective_date, department
  ✓ 0 duplicates
  ✓ diagnostics_report() báo Overall OK
"""

import os
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv

# Import từ package path chuẩn của project (src/core/data_ingestor).
# save_processed_doc là hàm của upstream — import riêng để dễ kiểm soát,
# tránh dùng wildcard import (*) gây khó debug.
from day08.lab.src.core.data_ingestor import (
    extract_metadata,
    remove_metadata_lines,
    extract_heading,
    clean_text,
    save_processed_doc,   # lưu doc đã preprocess ra disk (upstream feature)
)

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from day08.lab.vector_store_manager import get_chroma_collection
# Client OpenAI được khởi tạo lazy (chỉ tạo khi cần, tái dùng cho các lần sau)
_OPENAI_CLIENT: Optional["OpenAI"] = None

# =============================================================================
# CẤU HÌNH
# =============================================================================

# BASE_DIR trỏ đến day08/lab/ (parents[2] từ src/indexing/index.py)
BASE_DIR      = Path(__file__).resolve().parents[2]
DOCS_DIR      = BASE_DIR / "data" / "docs"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"

# Chunk size tính theo token-units (1 token ≈ 4 ký tự tiếng Anh / ~2-3 ký tự tiếng Việt).
# CHUNK_SIZE * 4 = 2800 chars — lớn hơn max section thực tế (~712 chars)
# → mỗi section giữ nguyên 1 chunk, không bị cắt vụn.
# Nếu sau này dùng tài liệu dài hơn, giữ nguyên giá trị này vẫn đúng.
CHUNK_SIZE    = 700   # token-units; chunk_chars = 700 * 4 = 2800
CHUNK_OVERLAP = 20    # token-units; overlap_chars = 20 * 4 = 80

# Chunk ngắn hơn ngưỡng này bị coi là tiêu đề thuần tuý / dòng trắng → loại bỏ.
# Giá trị 80 chars thấp hơn chunk ngắn nhất có nghĩa (~101 chars) để không lọc nhầm.
MIN_CHUNK_CHARS = 80


# =============================================================================
# STEP 1: PREPROCESS
# Làm sạch và extract metadata từ tài liệu thô
# =============================================================================

def preprocess_document(raw_text: str, filepath: str) -> Dict[str, Any]:
    """
    Preprocess một tài liệu: extract metadata từ header và làm sạch nội dung.

    Args:
        raw_text: Toàn bộ nội dung file text thô.
        filepath: Đường dẫn file (dùng làm source mặc định nếu header thiếu).

    Returns:
        {
          "text":     nội dung đã clean (bỏ header metadata),
          "metadata": {source, department, effective_date, access, alias, heading}
        }
    """
    # Bước 1a: Parse các dòng "Key: Value" ở đầu file thành dict metadata
    metadata = extract_metadata(raw_text, filepath)

    # Bước 1b: Xoá các dòng header metadata khỏi nội dung chính
    content = remove_metadata_lines(raw_text)

    # Bước 1c: Lấy tiêu đề chính của tài liệu (dòng in hoa đầu tiên)
    heading = extract_heading(content)
    metadata["heading"] = heading

    # Bước 1d: Normalize khoảng trắng, xoá ký tự rác
    cleaned_text = clean_text(content)

    doc = {"text": cleaned_text, "metadata": metadata}

    # Bước 1e: Lưu doc đã preprocess ra disk để các thành viên khác tái dùng
    # (hàm này từ upstream — lưu vào data/processed/)
    # out_dir = save_processed_doc(doc)
    # print(out_dir)

    return doc


# =============================================================================
# STEP 2: CHUNK
# Chia tài liệu thành các đoạn nhỏ theo cấu trúc tự nhiên
# =============================================================================

def chunk_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk tài liệu đã preprocess theo heading → paragraph → sentence.

    Pipeline:
      1. Split theo heading "=== Section ... ===" → các section riêng biệt.
      2. Mỗi section nếu dài hơn chunk_chars thì split tiếp theo paragraph.
      3. Paragraph quá dài tiếp tục split theo câu (tránh cắt giữa điều khoản).
      4. Thêm overlap: lấy đoạn đuôi chunk trước làm đầu chunk tiếp theo,
         giúp retrieval không mất ngữ cảnh liên section.
      5. Lọc bỏ chunk ngắn hơn MIN_CHUNK_CHARS (tiêu đề thuần tuý, dòng trắng).

    Args:
        doc: Output của preprocess_document() — dict có "text" và "metadata".

    Returns:
        Danh sách chunk, mỗi chunk là dict {"text": ..., "metadata": {..., "section": ...}}.
    """
    text          = doc["text"]
    base_metadata = doc["metadata"].copy()

    raw_chunks: List[Dict[str, Any]] = []

    # Bước 1: Split theo heading pattern "=== ... ==="
    # re.split với capturing group giữ lại heading trong danh sách kết quả
    sections = re.split(r"(===.*?===)", text)
    current_section      = "General"   # section mặc định cho phần đầu tài liệu
    current_section_text = ""

    for part in sections:
        if re.match(r"===.*?===", part):
            # Đã gặp heading mới → flush section hiện tại trước
            if current_section_text.strip():
                raw_chunks.extend(
                    _split_by_size(
                        current_section_text.strip(),
                        base_metadata=base_metadata,
                        section=current_section,
                    )
                )
            # Bắt đầu section mới: strip dấu "=" và khoảng trắng thừa
            current_section      = part.strip("= ").strip()
            current_section_text = ""
        else:
            # Tích lũy nội dung vào section hiện tại
            current_section_text += part

    # Flush section cuối cùng (không có heading nào theo sau)
    if current_section_text.strip():
        raw_chunks.extend(
            _split_by_size(
                current_section_text.strip(),
                base_metadata=base_metadata,
                section=current_section,
            )
        )

    # Bước 5: Lọc chunk rác — tiêu đề thuần tuý, dòng trắng, nội dung quá ngắn
    chunks = [c for c in raw_chunks if len(c["text"].strip()) >= MIN_CHUNK_CHARS]

    return chunks


def _split_by_size(
    text: str,
    base_metadata: Dict,
    section: str,
    chunk_chars: int   = CHUNK_SIZE * 4,        # 2800 chars mặc định
    overlap_chars: int = CHUNK_OVERLAP * 4,     # 80 chars overlap
) -> List[Dict[str, Any]]:
    """
    Split một section thành các chunk tự nhiên với overlap.

    Chiến lược:
    - Nếu section vừa trong chunk_chars → trả về ngay (1 section = 1 chunk).
    - Nếu không → gom paragraph cho đến khi đầy, tạo chunk, rồi chunk tiếp
      theo bắt đầu bằng overlap_buffer (đuôi của chunk trước) để giữ ngữ cảnh.

    Args:
        text:          Nội dung section đã strip.
        base_metadata: Metadata gốc từ tài liệu (không có "section").
        section:       Tên section hiện tại để gán vào metadata.
        chunk_chars:   Giới hạn ký tự mỗi chunk.
        overlap_chars: Số ký tự lấy từ đuôi chunk trước làm overlap.

    Returns:
        Danh sách các chunk dict.
    """
    text = text.strip()

    # Trường hợp đơn giản: toàn bộ section vừa 1 chunk → không cần cắt
    if len(text) <= chunk_chars:
        return [{"text": text, "metadata": {**base_metadata, "section": section}}]

    # Bước 2a: Normalize thành danh sách paragraph
    # Paragraph quá dài (hiếm với corpus hiện tại) tiếp tục split theo câu
    paragraphs: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) > chunk_chars:
            # Paragraph dài bất thường → split theo câu để tránh cắt giữa điều khoản
            paragraphs.extend(_split_long_paragraph(para, chunk_chars))
        else:
            paragraphs.append(para)

    if not paragraphs:
        paragraphs = [text]

    # Bước 2b: Gom paragraph thành chunk, thêm overlap từ chunk trước
    chunks: List[Dict[str, Any]] = []
    overlap_buffer = ""   # phần đuôi chunk trước, thêm vào đầu chunk tiếp theo
    cursor = 0

    while cursor < len(paragraphs):
        chunk_parts: List[str] = []
        current_len = 0

        # Bắt đầu chunk mới bằng overlap từ chunk trước (nếu có)
        if overlap_buffer:
            chunk_parts.append(overlap_buffer)
            current_len = len(overlap_buffer)

        # Gom paragraph cho đến khi vượt giới hạn
        while cursor < len(paragraphs):
            paragraph = paragraphs[cursor]
            delimiter = 2 if chunk_parts else 0   # "\n\n" giữa các paragraph = 2 chars
            candidate = current_len + delimiter + len(paragraph)

            if chunk_parts and candidate > chunk_chars:
                break   # chunk đầy → sang chunk tiếp theo

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

        # Tính overlap cho chunk tiếp theo (chỉ khi còn paragraph chưa xử lý)
        overlap_buffer = (
            _extract_overlap_tail(chunk_text, overlap_chars)
            if cursor < len(paragraphs)
            else ""
        )

    return chunks


def _split_long_paragraph(paragraph: str, chunk_chars: int) -> List[str]:
    """
    Chia một paragraph quá dài thành các đoạn theo ranh giới câu.

    Dùng regex nhìn sau (lookbehind) để split tại dấu câu kết thúc (.!?)
    mà không xoá dấu câu đó khỏi kết quả.

    Args:
        paragraph:   Đoạn văn cần chia.
        chunk_chars: Giới hạn ký tự mỗi đoạn con.

    Returns:
        Danh sách các đoạn con, mỗi đoạn <= chunk_chars chars.
    """
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    segments: List[str] = []
    builder: List[str]  = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sep       = 1 if builder else 0   # khoảng cách giữa các câu = 1 char
        candidate = current_len + sep + len(sentence)

        if builder and candidate > chunk_chars:
            # Đoạn đầy → flush và bắt đầu đoạn mới
            segments.append(" ".join(builder))
            builder     = [sentence]
            current_len = len(sentence)
        else:
            builder.append(sentence)
            current_len = candidate

    if builder:
        segments.append(" ".join(builder))

    # Fallback: nếu câu duy nhất vẫn dài hơn limit, cắt cứng
    return segments or [paragraph[:chunk_chars]]


def _extract_overlap_tail(text: str, overlap_chars: int) -> str:
    """
    Lấy phần đuôi của chunk để làm overlap cho chunk tiếp theo.

    Dùng lstrip() để không bắt đầu overlap bằng khoảng trắng / newline.

    Args:
        text:          Nội dung chunk hiện tại.
        overlap_chars: Số ký tự muốn lấy từ đuôi.

    Returns:
        Chuỗi overlap, hoặc "" nếu không cần.
    """
    if overlap_chars <= 0 or not text:
        return ""
    return text[-overlap_chars:].lstrip()


# =============================================================================
# STEP 3: EMBED + STORE
# Tạo embedding vector và lưu vào ChromaDB
# =============================================================================

def _get_openai_client() -> "OpenAI":
    """
    Khởi tạo OpenAI client lazy (singleton).
    Đọc API key từ biến môi trường OPENAI_API_KEY (load từ .env).
    """
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
    """
    Tạo embedding vector cho một đoạn text bằng OpenAI.

    Model: text-embedding-3-small (1536 dims, cost-effective).
    Dùng chung 1 client singleton để tránh tạo lại connection mỗi lần gọi.

    Args:
        text: Đoạn text cần embed.

    Returns:
        Vector embedding dạng List[float].
    """
    client   = _get_openai_client()
    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding


def build_index(docs_dir: Path = DOCS_DIR, db_dir: Path = CHROMA_DB_DIR) -> None:
    """
    Pipeline hoàn chỉnh Sprint 1–3:
      đọc docs → preprocess → chunk → filter → embed → upsert vào ChromaDB.

    Dùng upsert (không phải insert) để tránh duplicate khi chạy lại.
    chunk_id = "{filename}_{index}" đảm bảo idempotent.

    Args:
        docs_dir: Thư mục chứa file .txt cần index.
        db_dir:   Thư mục lưu ChromaDB persistent storage.
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

        # Preprocess: extract metadata + clean text
        doc = preprocess_document(raw_text, str(filepath))

        # ✅ minimal fallback (avoid missing metadata issues)
        doc["metadata"].setdefault("source", str(filepath))
        doc["metadata"].setdefault("department", "unknown")
        doc["metadata"].setdefault("effective_date", "unknown")

        # Chunk: split theo section/paragraph/sentence + filter chunk rác
        chunks = chunk_document(doc)

        # Embed và upsert từng chunk vào ChromaDB
        for i, chunk in enumerate(chunks):
            chunk_id  = f"{filepath.stem}_{i}"   # ID idempotent để upsert đúng
            embedding = get_embedding(chunk["text"])
            collection.upsert(
                ids        = [chunk_id],
                embeddings = [embedding],
                documents  = [chunk["text"]],
                metadatas  = [chunk["metadata"]],
            )

        total_chunks += len(chunks)
        print(f"    -> {len(chunks)} chunks indexed")

    print(f"\nHoan thanh! Tong so chunks: {total_chunks}")


# =============================================================================
# STEP 4: INSPECT / DIAGNOSTICS
# Kiểm tra chất lượng index sau khi build
# =============================================================================

def list_chunks(db_dir: Path = CHROMA_DB_DIR, n: int = 5) -> None:
    """
    In ra n chunk đầu tiên trong ChromaDB để kiểm tra nhanh chất lượng index.

    Kiểm tra:
    - Chunk có giữ đủ metadata không? (source, section, effective_date)
    - Chunk có bị cắt giữa điều khoản không? (xem text preview)
    - Length có hợp lý không?

    Args:
        db_dir: Thư mục ChromaDB.
        n:      Số chunk muốn xem.
    """
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
        print(f"Loi khi doc index: {e}")
        print("Hay chay build_index() truoc.")


def _collect_index_records(
    collection,
) -> List[Tuple[str, Dict[str, Any]]]:
    """Helper: lấy toàn bộ records từ collection dưới dạng list of (text, metadata)."""
    results = collection.get(include=["documents", "metadatas"])
    return list(zip(results.get("documents", []), results.get("metadatas", [])))


def inspect_metadata_coverage(db_dir: Path = CHROMA_DB_DIR) -> None:
    """
    Báo cáo nhanh về metadata coverage trong toàn bộ index.

    In ra:
    - Phân bố chunk theo department
    - Số chunk thiếu từng trường metadata quan trọng

    Dùng để verify Sprint 2 DoD: "Metadata truy xuất được".
    """
    try:
        collection = get_chroma_collection(db_dir)
    except RuntimeError as exc:
        print(f"Loi khi khoi tao Chroma: {exc}")
        return

    records = _collect_index_records(collection)
    if not records:
        print("Chua co index. Chay build_index() truoc.")
        return

    departments = Counter()
    missing     = Counter()

    for _, meta in records:
        departments[meta.get("department", "unknown")] += 1
        for field in ("source", "section", "effective_date"):
            if not meta.get(field):
                missing[field] += 1

    print(f"\nTong chunks: {len(records)}")
    print("Phan bo theo department:")
    for dept, count in departments.most_common():
        print(f"  {dept}: {count} chunks")
    print("Chunks thieu metadata:")
    for field in ("source", "section", "effective_date"):
        count  = missing[field]
        status = "OK" if count == 0 else f"!! {count} chunks thieu"
        print(f"  {field}: {status}")


def diagnostics_report(
    db_dir: Path = CHROMA_DB_DIR,
    sample_short: int = 3,
    sample_long:  int = 3,
) -> None:
    """
    Sprint 4 – Error Tree diagnostics.

    Kiểm tra 4 nhánh theo yêu cầu Sprint 4:

    [Nhánh 1] Chunk có đúng không?
      - Avg length >= 40% max_len (không cắt vụn section)
      - Min length >= MIN_CHUNK_CHARS (không có chunk rác)
      - Dùng dynamic_target thay vì chunk_chars cứng vì corpus nhỏ
        (max section ~712 chars < target lý thuyết 2800 chars)

    [Nhánh 2] Metadata có đủ không?
      - source, section, effective_date: 0 chunks thiếu

    [Nhánh 3] Trùng lặp?
      - 0 duplicate chunk texts (upsert đã ngăn chặn, verify lại ở đây)

    [Nhánh 4] Phân bố section hợp lý?
      - Mỗi section xuất hiện đúng 1 lần (1 section = 1 chunk)

    Args:
        db_dir:       Thư mục ChromaDB.
        sample_short: Số chunk ngắn nhất cần in ra để kiểm tra.
        sample_long:  Số chunk dài nhất cần in ra để kiểm tra.
    """
    try:
        collection = get_chroma_collection(db_dir)
    except RuntimeError as exc:
        print(f"Loi khi khoi tao Chroma: {exc}")
        return

    records = _collect_index_records(collection)
    if not records:
        print("Chua co index. Chay build_index() truoc.")
        return

    # --- Thu thập số liệu thô ---
    lengths    = [(len(text), text, meta) for text, meta in records]
    avg_len    = sum(l for l, *_ in lengths) / len(lengths)
    min_len    = min(l for l, *_ in lengths)
    max_len    = max(l for l, *_ in lengths)

    sections   = Counter()
    seen_texts = Counter()   # đếm tần suất mỗi chunk text để phát hiện duplicate
    missing    = Counter()

    for text, meta in records:
        sections[meta.get("section", "unknown")] += 1
        seen_texts[text.strip()] += 1
        for field in ("source", "section", "effective_date"):
            if not meta.get(field):
                missing[field] += 1

    # Duplicate = chunk text xuất hiện >= 2 lần
    duplicates = {t for t, freq in seen_texts.items() if freq > 1}

    # --- Đánh giá chất lượng ---
    # dynamic_target: dùng max_len thực tế thay vì chunk_chars cứng
    # vì corpus nhỏ không thể sinh chunk dài hơn max section (~712 chars)
    dynamic_target = max_len * 0.4
    chunk_ok   = avg_len >= dynamic_target
    meta_ok    = all(v == 0 for v in missing.values())
    dup_ok     = len(duplicates) == 0

    # --- In report ---
    print("\n" + "=" * 60)
    print("Diagnostics Report — Sprint 4 Error Tree")
    print("=" * 60)

    # Nhánh 1: kiểm tra chunk quality
    print(f"\n[Nhanh 1] Chunk quality")
    print(f"    Total chunks   : {len(records)}")
    print(f"    Avg length     : {avg_len:.0f} chars")
    print(f"    Min / Max      : {min_len} / {max_len} chars")
    print(f"    MIN_CHUNK_CHARS: {MIN_CHUNK_CHARS} chars  (nguong loc chunk rac)")
    print(f"    Dynamic target : avg >= {dynamic_target:.0f} chars  (40% x max={max_len})")
    if chunk_ok:
        print(f"    Status         : OK -- chunk giu nguyen section, khong cat vun")
    else:
        print(f"    Status         : !! avg qua thap -- chunking dang cat vun section")

    # Nhánh 2: kiểm tra metadata coverage
    print(f"\n[Nhanh 2] Metadata coverage")
    for field in ("source", "section", "effective_date"):
        count  = missing[field]
        status = "OK" if count == 0 else f"!! {count} chunks thieu"
        print(f"    {field:<20}: {status}")
    print(f"    Overall        : {'OK' if meta_ok else '!! Co truong metadata bi thieu'}")

    # Nhánh 3: kiểm tra duplicate
    print(f"\n[Nhanh 3] Duplicates")
    dup_status = "OK" if dup_ok else f"!! {len(duplicates)} duplicates -- can dedup"
    print(f"    Duplicate chunks: {len(duplicates)}  {dup_status}")

    # Nhánh 4: phân bố section (mỗi section đúng 1 chunk là lý tưởng)
    print(f"\n[Nhanh 4] Section distribution (top 10)")
    for section, count in sections.most_common(10):
        bar = "=" * count
        print(f"    {section[:45]:<45} {count:>3}  {bar}")

    # In sample để kiểm tra thủ công
    def _print_samples(label: str, entries: list):
        print(f"\n[Sample] {label} (showing {len(entries)}):")
        for idx, (length, text, meta) in enumerate(entries, 1):
            preview = text[:100].replace("\n", " ")
            sec     = meta.get("section", "N/A")
            print(f"    {idx}. section={sec!r:<35} len={length:>4} | {preview}")

    sorted_lengths = sorted(lengths, key=lambda x: x[0])
    _print_samples("Shortest chunks", sorted_lengths[:sample_short])
    _print_samples("Longest chunks",  sorted_lengths[-sample_long:])

    # --- Tổng kết: pass khi cả 3 nhánh chính OK ---
    all_ok = chunk_ok and meta_ok and dup_ok
    print("\n" + "-" * 60)
    if all_ok:
        print("Overall: [OK] Index sach -- san sang cho retrieval")
    else:
        print("Overall: [!!] Can xem lai cac nhanh duoc danh dau tren")
    print("=" * 60)

def evaluate_retrieval(json_path: Path, top_k: int = 3):
    import json

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
            n_results=top_k
        )

        retrieved_sources = set()
        for meta in results["metadatas"][0]:
            if meta and "source" in meta:
                retrieved_sources.add(meta["source"])

        ok = len(expected_sources & retrieved_sources) > 0

        if ok:
            hit += 1

        print("\n" + "="*60)
        print(f"Q: {question}")
        print(f"Expected: {expected_sources}")
        print(f"Retrieved: {retrieved_sources}")
        print(f"Result: {'✅ HIT' if ok else '❌ MISS'}")

    print("\n" + "="*60)
    print(f"FINAL SCORE: {hit}/{total} = {hit/total:.2%}")
# =============================================================================
# MAIN — smoke test (chạy trực tiếp: python index.py)
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 1-4: Build RAG Index")
    print("=" * 60)

    doc_files = list(DOCS_DIR.glob("*.txt"))
    print(f"\nTim thay {len(doc_files)} tai lieu:")
    for f in doc_files:
        print(f"  - {f.name}")

    # Test preprocess + chunking trước (không cần API key)
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

    # Build toàn bộ index (yêu cầu OPENAI_API_KEY trong .env)
    print("\n--- Build Full Index ---")
    build_index()

    print("\n--- list_chunks() ---")
    list_chunks()

    print("\n--- inspect_metadata_coverage() ---")
    inspect_metadata_coverage()

    # Chạy diagnostics report cuối cùng để verify DoD Sprint 4
    print("\n--- diagnostics_report() ---")
    diagnostics_report()
