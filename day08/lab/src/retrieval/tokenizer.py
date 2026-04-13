import re
import logging
from underthesea import word_tokenize

logger = logging.getLogger(__name__)

class MaskingTokenizer:
    """
    Tokenizer với cơ chế Masking-Unmasking để bảo vệ các từ khóa đặc biệt khỏi việc bị tách vụn bởi underthesea.
    """
    def __init__(self):
        # Các pattern ưu tiên cần giữ lại
        self.patterns = [
            r"[A-Z]+-\d+",           # Mã lỗi, ví dụ: ERR-403
            r"\d{1,3}(?:\.\d{1,3}){3}", # IP address
            r"(?i)Ticket\sP\d"        # e.g., Ticket P1
        ]
        
    def tokenize(self, text: str) -> list[str]:
        """
        Thực hiện chuỗi: Masking -> Tokenization -> Unmasking.
        Trả về list các tokens theo định dạng lowercase để BM25 hoạt động tốt.
        """
        placeholder_map = {}
        masked_text = text
        
        # 1. Masking
        for p_idx, pattern in enumerate(self.patterns):
            matches = re.finditer(pattern, masked_text)
            for m_idx, match in enumerate(matches):
                original_str = match.group()
                placeholder = f"__MASK_{p_idx}_{m_idx}__"
                placeholder_map[placeholder] = original_str
                # Thay thế string gốc bằng placeholder
                masked_text = masked_text.replace(original_str, placeholder, 1)
        
        # 2. Tokenization với underthesea
        tokenized_text = word_tokenize(masked_text, format="text")
        
        # 3. Unmasking và xử lý tokenize array
        tokens_list = []
        # underthesea word_tokenize với format="text" nối các từ ghép bằng dấu _, token phân cách bằng dấu cách
        for word in tokenized_text.split():
            # Check nếu word chứa placeholder thì unmask
            for placeholder, original_str in placeholder_map.items():
                if placeholder in word:
                    word = word.replace(placeholder, original_str)
            tokens_list.append(word.lower())

        logger.debug(f"[TOKENIZER_TRACE] Parsed Tokens: {tokens_list}")
        
        return tokens_list
