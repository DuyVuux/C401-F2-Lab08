"""
Offline A/B Testing, Benchmarking, and Confidence Scorecard logic.
"""
import json
import os
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from dotenv import load_dotenv
from src.core.schemas import Document, AnswerResponse
from src.core.logger_config import get_logger
from src.core.telemetry import diagnostic_decorator

load_dotenv()
logger = get_logger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent.parent / "results"


class PipelineEvaluator:
    """
    Executes standard queries against the system and evaluates quality
    using programmatic heuristics or LLM-as-a-Judge.
    """

    def __init__(self) -> None:
        """Initializes the verification utilities."""
        logger.info("[INFO] [PIPELINE_INIT] Initializing Evaluator Scorecard module.")

    # =========================================================================
    # LLM-AS-JUDGE HELPER
    # =========================================================================

    def _call_judge(self, prompt: str) -> Dict[str, Any]:
        """
        Gọi LLM để chấm điểm. Trả về dict {"score": int, "reason": str}.
        Dùng temperature=0 để kết quả chấm nhất quán giữa các lần chạy.
        Nếu parse JSON thất bại, trả về score=None và log lỗi.
        """
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an objective RAG evaluation judge. "
                        "Always respond with valid JSON only, no extra text. "
                        'Format: {"score": <integer 1-5>, "reason": "<short explanation>"}'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[ERROR] [JUDGE] JSON parse error: {raw[:100]}")
            return {"score": None, "reason": f"JSON parse error: {raw[:100]}"}

    # =========================================================================
    # SCORING FUNCTIONS — 4 metrics
    # =========================================================================

    def score_faithfulness(self, answer: str, chunks_used: List[Document]) -> Dict[str, Any]:
        """
        Faithfulness: Câu trả lời có bám đúng chứng cứ đã retrieve không?
        Câu hỏi: Model có tự bịa thêm thông tin ngoài retrieved context không?

        Thang điểm 1-5:
          5: Mọi thông tin trong answer đều có trong retrieved chunks
          4: Gần như hoàn toàn grounded, 1 chi tiết nhỏ chưa chắc chắn
          3: Phần lớn grounded, một số thông tin có thể từ model knowledge
          2: Nhiều thông tin không có trong retrieved chunks
          1: Câu trả lời không grounded, phần lớn là model bịa

        Dùng LLM-as-Judge (Cách 2) — bonus +2 điểm theo SCORING.md.
        Trả về dict với: score (1-5) và notes (lý do)
        """
        context = "\n---\n".join(doc.text for doc in chunks_used)
        if not context:
            return {"score": 1, "notes": "Không có chunks được retrieve — không thể grounded"}

        prompt = f"""Given these retrieved chunks:
{context}

And this answer:
{answer}

Rate the faithfulness on a scale of 1-5.
5 = completely grounded in the provided context.
4 = almost all claims grounded; at most 1 minor unsupported detail.
3 = mostly grounded, some info may come from model knowledge.
2 = several claims not in the retrieved context.
1 = answer contains information not in the context.
Output JSON: {{"score": <int>, "reason": "<string>"}}"""

        result = self._call_judge(prompt)
        return {"score": result.get("score"), "notes": result.get("reason", "")}

    def score_answer_relevance(self, query: str, answer: str) -> Dict[str, Any]:
        """
        Answer Relevance: Answer có trả lời đúng câu hỏi người dùng hỏi không?
        Câu hỏi: Model có bị lạc đề hay trả lời đúng vấn đề cốt lõi không?

        Thang điểm 1-5:
          5: Answer trả lời trực tiếp và đầy đủ câu hỏi
          4: Trả lời đúng nhưng thiếu vài chi tiết phụ
          3: Trả lời có liên quan nhưng chưa đúng trọng tâm
          2: Trả lời lạc đề một phần
          1: Không trả lời câu hỏi

        TODO Sprint 4: Implement tương tự score_faithfulness
        """
        prompt = f"""Given this question:
{query}

And this answer:
{answer}

Rate the answer relevance on a scale of 1-5.
5 = directly and completely answers the question asked.
4 = answers correctly but misses a few minor details.
3 = related to the question but doesn't address the core issue.
2 = partially off-topic.
1 = does not answer the question at all.
Output JSON: {{"score": <int>, "reason": "<string>"}}"""

        result = self._call_judge(prompt)
        return {"score": result.get("score"), "notes": result.get("reason", "")}

    def score_context_recall(
        self, chunks_used: List[Document], expected_sources: List[str]
    ) -> Dict[str, Any]:
        """
        Context Recall: Retriever có mang về đủ evidence cần thiết không?
        Câu hỏi: Expected source có nằm trong retrieved chunks không?

        Đây là metric đo retrieval quality, không phải generation quality.

        Cách tính đơn giản:
            recall = (số expected source được retrieve) / (tổng số expected sources)

        Ví dụ:
            expected_sources = ["policy/refund-v4.pdf", "sla-p1-2026.pdf"]
            retrieved_sources = ["policy/refund-v4.pdf", "helpdesk-faq.md"]
            recall = 1/2 = 0.5

        TODO Sprint 4:
        1. Lấy danh sách source từ chunks_used
        2. Kiểm tra xem expected_sources có trong retrieved sources không
        3. Tính recall score
        """
        if not expected_sources:
            return {"score": None, "recall": None, "notes": "No expected sources"}

        retrieved_sources = {doc.metadata.get("source", "") for doc in chunks_used}

        # Kiểm tra partial match (tên file) vì source paths có thể khác format
        found = 0
        missing = []
        for expected in expected_sources:
            expected_name = expected.split("/")[-1].replace(".pdf", "").replace(".md", "")
            matched = any(expected_name.lower() in r.lower() for r in retrieved_sources)
            if matched:
                found += 1
            else:
                missing.append(expected)

        recall = found / len(expected_sources)
        return {
            "score": round(recall * 5),
            "recall": recall,
            "found": found,
            "missing": missing,
            "notes": f"Retrieved: {found}/{len(expected_sources)} expected sources"
                     + (f". Missing: {missing}" if missing else ""),
        }

    def score_completeness(
        self, query: str, answer: str, expected_answer: str
    ) -> Dict[str, Any]:
        """
        Completeness: Answer có thiếu điều kiện ngoại lệ hoặc bước quan trọng không?
        Câu hỏi: Answer có bao phủ đủ thông tin so với expected_answer không?

        Thang điểm 1-5:
          5: Answer bao gồm đủ tất cả điểm quan trọng trong expected_answer
          4: Thiếu 1 chi tiết nhỏ
          3: Thiếu một số thông tin quan trọng
          2: Thiếu nhiều thông tin quan trọng
          1: Thiếu phần lớn nội dung cốt lõi

        TODO Sprint 4:
        Option 1 — Chấm thủ công: So sánh answer vs expected_answer và chấm.
        Option 2 — LLM-as-Judge:
            "Compare the model answer with the expected answer.
             Rate completeness 1-5. Are all key points covered?
             Output: {'score': int, 'missing_points': [str]}"
        """
        if not expected_answer:
            return {"score": None, "notes": "Không có expected_answer để so sánh"}

        # Dùng LLM-as-Judge (Option 2)
        prompt = f"""Compare the model answer with the expected answer.

Question: {query}

Expected answer (ground truth):
{expected_answer}

Model answer:
{answer}

Rate completeness 1-5. Are all key points covered?
5 = covers all key points from the expected answer.
4 = missing only 1 minor detail.
3 = missing some important information.
2 = missing several important points.
1 = missing most of the core content.
Output JSON: {{"score": <int>, "reason": "<string>"}}"""

        result = self._call_judge(prompt)
        return {"score": result.get("score"), "notes": result.get("reason", "")}

    # =========================================================================
    # NDCG METRIC
    # =========================================================================

    def calculate_ndcg(self, predictions: List[str], ground_truth: List[str]) -> float:
        """
        Calculates Normalized Discounted Cumulative Gain based on ranking precision.

        TODO [Sprint 4 - NDCG Metric Calculation]:
        - DCG = sum(relevance_i / log2(i+2)) với i là rank (0-indexed)
        - IDCG = DCG của ranking lý tưởng (ground_truth đứng đầu hết)
        - NDCG = DCG / IDCG
        """
        import math

        def dcg(ranked: List[str], relevant: List[str]) -> float:
            return sum(
                1.0 / math.log2(i + 2)
                for i, doc in enumerate(ranked)
                if doc in relevant
            )

        actual_dcg = dcg(predictions, ground_truth)
        ideal_dcg = dcg(ground_truth, ground_truth)
        if ideal_dcg == 0:
            return 0.0
        return round(actual_dcg / ideal_dcg, 4)

    # =========================================================================
    # BENCHMARK RUNNER
    # =========================================================================

    @diagnostic_decorator
    def run_benchmark(self, dataset_path: str) -> Dict[str, float]:
        """
        Executes a rigorous, 4-metric evaluation pass over the entire pipeline.

        Args:
            dataset_path (str): Relative path to benchmark ground truths (JSON/CSV).

        Returns:
            Dict[str, float]: Aggregate metrics (Precision, Recall, Faithfulness, Context Relevance).

        TODO [Sprint 4 - Benchmark Flow]:
        - Đọc tập test case
        - Khởi tạo RAGPipeline và invoke cho từng câu hỏi
        - Tính toán 4 metrics chính
        - Hỗ trợ ghi log delta A/B để đưa kết quả ra Tuning Log
        """
        from src.retrieval.rag_answer import RAGPipeline

        logger.info(f"[INFO] [BENCHMARK] Initiating run for dataset: {dataset_path}")

        with open(dataset_path, "r", encoding="utf-8") as f:
            test_questions = json.load(f)

        pipeline = RAGPipeline()
        results = []

        for q in test_questions:
            qid = q["id"]
            query = q["question"]
            expected_answer = q.get("expected_answer", "")
            expected_sources = q.get("expected_sources", [])
            category = q.get("category", "")

            logger.info(f"[INFO] [BENCHMARK] Running [{qid}]: {query}")

            try:
                chunks_used = pipeline.retrieve_documents(query)
                response: AnswerResponse = pipeline.generate_grounded_answer(query, chunks_used)
                answer = response.answer
            except NotImplementedError:
                answer = "PIPELINE_NOT_IMPLEMENTED"
                chunks_used = []
            except Exception as e:
                logger.error(f"[ERROR] [{qid}] Pipeline error: {e}")
                answer = f"ERROR: {e}"
                chunks_used = []

            faith = self.score_faithfulness(answer, chunks_used)
            relevance = self.score_answer_relevance(query, answer)
            recall = self.score_context_recall(chunks_used, expected_sources)
            complete = self.score_completeness(query, answer, expected_answer)

            row = {
                "id": qid,
                "category": category,
                "query": query,
                "answer": answer,
                "faithfulness": faith["score"],
                "faithfulness_notes": faith["notes"],
                "relevance": relevance["score"],
                "relevance_notes": relevance["notes"],
                "context_recall": recall["score"],
                "context_recall_notes": recall["notes"],
                "completeness": complete["score"],
                "completeness_notes": complete["notes"],
            }
            results.append(row)
            logger.info(
                f"[INFO] [{qid}] F={faith['score']} R={relevance['score']} "
                f"Rc={recall['score']} C={complete['score']}"
            )

        # Tính averages
        metrics = ["faithfulness", "relevance", "context_recall", "completeness"]
        averages = {}
        for metric in metrics:
            scores = [r[metric] for r in results if r[metric] is not None]
            averages[metric] = round(sum(scores) / len(scores), 2) if scores else None

        logger.info(f"[INFO] [BENCHMARK] Averages: {averages}")

        # Lưu kết quả CSV
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        csv_path = RESULTS_DIR / f"benchmark_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"[INFO] [BENCHMARK] Results saved to {csv_path}")

        return averages
