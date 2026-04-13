"""
data_ingestor.py
================
Chịu trách nhiệm:
- Clean text (OCR, noise, normalize)
- Extract & normalize metadata
- Support preprocess_document() trong index.py

Design principle:
"Garbage in → Garbage out" → đảm bảo input cho chunking & embedding là clean nhất.
"""

import re
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


# =============================================================================
# CLEANING FUNCTIONS
# =============================================================================

def clean_text(text: str) -> str:
    """
    Làm sạch text:
    - Loại bỏ ký tự rác OCR
    - Normalize bullet points
    - Chuẩn hóa khoảng trắng & newline
    """
    # Remove non-standard unicode (giữ tiếng Việt)
    text = re.sub(r"[^\x00-\x7F\u00C0-\u1EF9\n]", " ", text)

    # Normalize bullet points
    text = re.sub(r"[•●▪]", "-", text)

    # Remove multiple dots
    text = re.sub(r"\.{2,}", ".", text)

    # Normalize spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Normalize newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =============================================================================
# METADATA NORMALIZATION
# =============================================================================

def normalize_date(date_str: str) -> str:
    """
    Chuẩn hóa date về format YYYY-MM-DD
    """
    if not date_str:
        return "unknown"

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except:
            continue

    return "unknown"


# =============================================================================
# METADATA EXTRACTION
# =============================================================================

def extract_metadata(raw_text: str, filepath: str) -> Dict[str, Any]:
    """
    Extract metadata từ header + content

    Mandatory:
    - source
    - section (chunk level)
    - effective_date

    Optional:
    - department
    - access
    - alias
    """
    lines = raw_text.split("\n")

    metadata = {
        "source": filepath,
        "department": "unknown",
        "effective_date": "unknown",
        "access": "internal",
        "alias": None,
    }

    # Extract structured metadata (Key: Value)
    meta_patterns = {
        "department": r"^Department:",
        "effective_date": r"^Effective Date:",
        "access": r"^Access:",
        "source": r"^Source:",
    }

    for line in lines[:10]:  # chỉ scan header
        clean_line = line.strip()

        for key, pattern in meta_patterns.items():
            if re.match(pattern, clean_line, re.IGNORECASE):
                value = clean_line.split(":", 1)[1].strip()

                if key == "effective_date":
                    metadata[key] = normalize_date(value)
                else:
                    metadata[key] = value

    # Extract alias (versioning support)
    alias_match = re.search(
        r'trước đây có tên "(.*?)"', raw_text, re.IGNORECASE
    )
    if alias_match:
        metadata["alias"] = alias_match.group(1)

    return metadata


# =============================================================================
# CONTENT EXTRACTION
# =============================================================================

def remove_metadata_lines(raw_text: str) -> str:
    """
    Loại bỏ các dòng metadata header khỏi content
    """
    lines = raw_text.split("\n")
    content_lines = []

    meta_patterns = [
        r"^Source:",
        r"^Department:",
        r"^Effective Date:",
        r"^Access:",
    ]

    for line in lines:
        clean_line = line.strip()

        if any(re.match(p, clean_line, re.IGNORECASE) for p in meta_patterns):
            continue

        content_lines.append(line)

    return "\n".join(content_lines)


# =============================================================================
# HEADING EXTRACTION
# =============================================================================

def extract_heading(text: str) -> str:
    """
    Lấy heading (dòng đầu viết hoa)
    """
    for line in text.split("\n"):
        clean_line = line.strip()
        if clean_line and clean_line.isupper():
            return clean_line

    return "UNKNOWN"

def save_processed_doc(doc, output_dir="data/processed"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # lấy tên file từ source
    source = doc["metadata"].get("source", "unknown")
    filename = Path(source).stem + ".json"

    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    return output_path