"""
Unit tests for Evaluator Scorecard and A/B rules in Sprint 5.
"""
import pytest
import logging
from src.evaluation.evaluator import PipelineEvaluator

def test_eval_metrics_logging(caplog):
    caplog.set_level(logging.INFO)
    
    evaluator = PipelineEvaluator()
    mock_test_set = [
        {
            "query": "Q1: Điểm tuyệt đối",
            "mock_scores": {"faithfulness": 5, "relevance": 5, "recall": 5, "completeness": 5},
            "note": "Perfect"
        },
        {
            "query": "Q2: Recall thấp",
            "mock_scores": {"faithfulness": 5, "relevance": 4, "recall": 2, "completeness": 3},
            "note": "Missing context"
        },
        {
            "query": "Q3: Completeness thấp",
            "mock_scores": {"faithfulness": 4, "relevance": 4, "recall": 4, "completeness": 2},
            "note": "Incomplete answer"
        }
    ]
    
    res = evaluator.run_evaluation_scorecard(mock_test_set, is_mock=True)
    
    assert res["faithfulness"] == pytest.approx(14.0 / 3)
    assert res["relevance"] == pytest.approx(13.0 / 3)
    assert res["recall"] == pytest.approx(11.0 / 3)
    assert res["completeness"] == pytest.approx(10.0 / 3)
    
    # Assert logs format
    assert "[EVAL_START] Booting" in caplog.text
    assert "[EVAL_SCORING] Query=" in caplog.text
    assert "Faithfulness: 4.7/5.0" in caplog.text

def test_ab_rule_violation(caplog):
    caplog.set_level(logging.INFO)
    evaluator = PipelineEvaluator()
    
    baseline = {"faithfulness": 4.0, "relevance": 4.0}
    variant = {"faithfulness": 4.5, "relevance": 4.0}
    
    # Test valid change
    evaluator.compare_ab_variants(baseline, variant, ["hybrid_retrieval"])
    assert "[AB_TESTING] Changed Variable: hybrid_retrieval. Delta improvement detected in faithfulness." in caplog.text
    assert "A/B Rule Violation" not in caplog.text
    
    caplog.clear()
    
    # Test invalid change
    evaluator.compare_ab_variants(baseline, variant, ["chunk_size", "hybrid_retrieval"])
    assert "A/B Rule Violation: You changed [chunk_size, hybrid_retrieval]. Only 1 variable allowed!" in caplog.text
