"""
Test suite for Sales MAS backend.
Run with: pytest tests/ -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Unit tests: signal tasks ──────────────────────────────────────────────────

def test_firmographic_task_returns_dict():
    from tasks.signal_tasks import collect_firmographic_signals
    prospect = {
        "company_name": "Acme",
        "company_size": "51-200",
        "industry": "SaaS",
        "tech_stack": ["Salesforce"],
    }
    result = collect_firmographic_signals.run(prospect)
    assert isinstance(result, dict)
    assert "signal_strength" in result
    assert result["signal_strength"] > 0


def test_firmographic_icp_fit_high():
    from tasks.signal_tasks import collect_firmographic_signals
    prospect = {"company_size": "201-500", "industry": "SaaS"}
    result = collect_firmographic_signals.run(prospect)
    assert result["icp_fit"] == "high"


def test_engagement_demo_request_boosts_score():
    from tasks.signal_tasks import collect_engagement_signals
    prospect = {"event_type": "demo_request"}
    result = collect_engagement_signals.run(prospect)
    assert result["signal_strength"] >= 70


def test_engagement_email_open_boosts_score():
    from tasks.signal_tasks import collect_engagement_signals
    prospect = {"event_type": "email_open"}
    result = collect_engagement_signals.run(prospect)
    assert result["signal_strength"] > 30


def test_intent_task_returns_dict():
    from tasks.signal_tasks import collect_intent_signals
    result = collect_intent_signals.run({"company_name": "TestCo"})
    assert isinstance(result, dict)
    assert "intent_score" in result
    assert 0 <= result["intent_score"] <= 100


def test_social_task_returns_dict():
    from tasks.signal_tasks import collect_social_signals
    result = collect_social_signals.run({"company_name": "TestCo"})
    assert isinstance(result, dict)
    assert "signal_strength" in result


def test_historical_task_returns_dict():
    from tasks.signal_tasks import collect_historical_signals
    result = collect_historical_signals.run({"email": "test@test.com"})
    assert isinstance(result, dict)
    assert "signal_strength" in result


# ── Unit tests: RAG pipeline ──────────────────────────────────────────────────

def test_detect_modality_text():
    from rag.pipeline import detect_modality
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello world")
        path = f.name
    assert detect_modality(path) == "text"


def test_detect_modality_image():
    from rag.pipeline import detect_modality
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    assert detect_modality(path) == "ocr"


def test_ingest_text_directly():
    from rag.pipeline import ingest_text_directly
    result = ingest_text_directly(
        "Acme Corp is an ideal ICP with 200 employees in SaaS sector.",
        {"test": True},
    )
    assert result["chunks_indexed"] >= 1


def test_retrieve_context_returns_string():
    from rag.pipeline import retrieve_context, seed_knowledge_base
    seed_knowledge_base()
    context = retrieve_context("SaaS company 50-200 employees")
    assert isinstance(context, str)
    assert len(context) > 0


# ── Unit tests: LangGraph graph ───────────────────────────────────────────────

def test_graph_builds_without_error():
    from graph.scoring_graph import build_graph
    graph = build_graph()
    assert graph is not None


def test_aggregate_node_handles_missing_signals():
    from graph.scoring_graph import aggregate_node
    state = {
        "prospect_data": {"company_name": "Test"},
        "signals": {},
        "rag_context": "",
        "score": 0,
        "grade": "D",
        "rationale": "",
        "recommended_action": "",
        "requires_human_review": False,
        "routing_decision": "",
        "error": None,
    }
    result = aggregate_node(state)
    assert result.get("error") is not None


def test_route_node_high_score():
    from graph.scoring_graph import route_node
    state = {
        "score": 85,
        "requires_human_review": False,
        "prospect_data": {},
        "signals": {},
        "rag_context": "",
        "grade": "A",
        "rationale": "",
        "recommended_action": "",
        "routing_decision": "",
        "error": None,
    }
    result = route_node(state)
    assert result["routing_decision"] == "rep_notify"


def test_route_node_borderline_score():
    from graph.scoring_graph import route_node
    state = {
        "score": 60,
        "requires_human_review": True,
        "prospect_data": {},
        "signals": {},
        "rag_context": "",
        "grade": "C",
        "rationale": "",
        "recommended_action": "",
        "routing_decision": "",
        "error": None,
    }
    result = route_node(state)
    assert result["routing_decision"] == "human_review"


def test_route_node_low_score():
    from graph.scoring_graph import route_node
    state = {
        "score": 20,
        "requires_human_review": False,
        "prospect_data": {},
        "signals": {},
        "rag_context": "",
        "grade": "D",
        "rationale": "",
        "recommended_action": "",
        "routing_decision": "",
        "error": None,
    }
    result = route_node(state)
    assert result["routing_decision"] == "deprioritize"


# ── Unit tests: store ─────────────────────────────────────────────────────────

def test_save_and_retrieve_prospect():
    from api.store import save_prospect, get_prospect
    save_prospect("test-001", {"company_name": "Acme", "score": 75})
    result = get_prospect("test-001")
    assert result["company_name"] == "Acme"
    assert result["score"] == 75


def test_list_prospects_sorted_by_score():
    from api.store import save_prospect, list_prospects
    save_prospect("p-low", {"score": 20, "company_name": "Low"})
    save_prospect("p-high", {"score": 90, "company_name": "High"})
    results = list_prospects()
    scores = [p["score"] for p in results]
    assert scores == sorted(scores, reverse=True)


def test_review_queue():
    from api.store import add_to_review_queue, get_review_queue, resolve_review
    add_to_review_queue("r-001", {"prospect_id": "r-001", "company_name": "Border Inc"})
    queue = get_review_queue()
    ids = [p["prospect_id"] for p in queue]
    assert "r-001" in ids
    resolve_review("r-001")
    queue2 = get_review_queue()
    ids2 = [p["prospect_id"] for p in queue2]
    assert "r-001" not in ids2
