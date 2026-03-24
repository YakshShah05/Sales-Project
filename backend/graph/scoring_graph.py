import os
import json
from typing import TypedDict, Optional, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
# from langchain.schema import HumanMessage, SystemMessage
from langchain_core.messages import HumanMessage, SystemMessage
from rag.pipeline import retrieve_context

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")


class ProspectState(TypedDict):
    """State carried through all LangGraph nodes."""
    prospect_data: dict
    signals: dict
    rag_context: str
    score: float
    grade: str
    rationale: str
    recommended_action: str
    requires_human_review: bool
    routing_decision: str
    error: Optional[str]


def get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=0.1,
        max_tokens=1024,
    )


def aggregate_node(state: ProspectState) -> ProspectState:
    """Node 1: Validate and normalise aggregated signals from Celery workers."""
    signals = state.get("signals", {})

    if not signals:
        return {**state, "error": "No signals available for scoring"}

    composite = signals.get("composite_signal_score", 0)

    for key in ["firmographic", "intent", "engagement", "social", "historical"]:
        if signals.get(key) is None:
            signals[key] = {"signal_strength": 0, "note": "agent_failed_gracefully"}

    return {**state, "signals": signals}


def rag_enrich_node(state: ProspectState) -> ProspectState:
    """Node 2: Retrieve context from both text and OCR vector stores."""
    if state.get("error"):
        return state

    prospect = state["prospect_data"]
    query = (
        f"company {prospect.get('company_name', '')} "
        f"industry {prospect.get('industry', '')} "
        f"size {prospect.get('company_size', '')} "
        f"sales intelligence deal history"
    )

    context = retrieve_context(query, k=4)
    return {**state, "rag_context": context}


def score_node(state: ProspectState) -> ProspectState:
    """Node 3: LLM scoring using Groq Llama 3 8B with retrieved context."""
    if state.get("error"):
        return {**state, "score": 0, "grade": "D", "rationale": "Scoring failed", "recommended_action": "Skip"}

    llm = get_llm()
    signals = state["signals"]
    prospect = state["prospect_data"]
    context = state.get("rag_context", "")

    prompt = f"""You are a B2B sales intelligence AI. Score this prospect from 0-100 and provide actionable guidance.

PROSPECT:
- Company: {prospect.get('company_name')}
- Contact: {prospect.get('contact_name')}
- Industry: {prospect.get('industry', 'Unknown')}
- Company size: {prospect.get('company_size', 'Unknown')}
- Event: {prospect.get('event_type')}

SIGNAL DATA:
Firmographic: {json.dumps(signals.get('firmographic', {}), indent=2)}
Buying Intent: {json.dumps(signals.get('intent', {}), indent=2)}
Engagement: {json.dumps(signals.get('engagement', {}), indent=2)}
Social: {json.dumps(signals.get('social', {}), indent=2)}
Historical CRM: {json.dumps(signals.get('historical', {}), indent=2)}
Composite signal score: {signals.get('composite_signal_score', 0):.1f}

RETRIEVED SALES CONTEXT:
{context[:1500]}

Respond ONLY with valid JSON in this exact format:
{{
  "score": <number 0-100>,
  "grade": "<A|B|C|D>",
  "rationale": "<one sentence a sales rep can read in 5 seconds>",
  "recommended_action": "<specific next step>",
  "requires_human_review": <true|false>
}}

Grade thresholds: A=80-100, B=60-79, C=40-59, D=0-39
Flag for human review if score is 55-65 (borderline cases)."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())

        return {
            **state,
            "score": float(result.get("score", 0)),
            "grade": result.get("grade", "D"),
            "rationale": result.get("rationale", ""),
            "recommended_action": result.get("recommended_action", ""),
            "requires_human_review": result.get("requires_human_review", False),
        }
    except Exception as e:
        composite = signals.get("composite_signal_score", 0)
        score = min(composite, 100)
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
        return {
            **state,
            "score": score,
            "grade": grade,
            "rationale": f"Auto-scored based on signal composite ({score:.0f}/100)",
            "recommended_action": "Review manually" if score > 70 else "Add to nurture sequence",
            "requires_human_review": 55 <= score <= 65,
        }


def route_node(state: ProspectState) -> ProspectState:
    """Node 4: Conditional routing based on score."""
    score = state.get("score", 0)
    requires_review = state.get("requires_human_review", False)

    if requires_review or (55 <= score <= 65):
        routing = "human_review"
    elif score >= 70:
        routing = "rep_notify"
    elif score >= 40:
        routing = "nurture"
    else:
        routing = "deprioritize"

    return {**state, "routing_decision": routing}


def should_continue(state: ProspectState) -> str:
    """Conditional edge: determine next node after routing."""
    routing = state.get("routing_decision", "deprioritize")
    return routing


def rep_notify_node(state: ProspectState) -> ProspectState:
    return {**state, "routing_decision": "rep_notify"}


def human_review_node(state: ProspectState) -> ProspectState:
    return {**state, "routing_decision": "human_review"}


def nurture_node(state: ProspectState) -> ProspectState:
    return {**state, "routing_decision": "nurture"}


def deprioritize_node(state: ProspectState) -> ProspectState:
    return {**state, "routing_decision": "deprioritize"}


def build_graph() -> StateGraph:
    """Build and compile the LangGraph agent graph."""
    graph = StateGraph(ProspectState)

    graph.add_node("aggregate", aggregate_node)
    graph.add_node("rag_enrich", rag_enrich_node)
    graph.add_node("score", score_node)
    graph.add_node("route", route_node)
    graph.add_node("rep_notify", rep_notify_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("nurture", nurture_node)
    graph.add_node("deprioritize", deprioritize_node)

    graph.set_entry_point("aggregate")
    graph.add_edge("aggregate", "rag_enrich")
    graph.add_edge("rag_enrich", "score")
    graph.add_edge("score", "route")

    graph.add_conditional_edges(
        "route",
        should_continue,
        {
            "rep_notify": "rep_notify",
            "human_review": "human_review",
            "nurture": "nurture",
            "deprioritize": "deprioritize",
        },
    )

    graph.add_edge("rep_notify", END)
    graph.add_edge("human_review", END)
    graph.add_edge("nurture", END)
    graph.add_edge("deprioritize", END)

    return graph.compile()


compiled_graph = build_graph()


def run_scoring_graph(prospect_data: dict, signals: dict) -> dict:
    """Run the full LangGraph scoring pipeline."""
    initial_state: ProspectState = {
        "prospect_data": prospect_data,
        "signals": signals,
        "rag_context": "",
        "score": 0.0,
        "grade": "D",
        "rationale": "",
        "recommended_action": "",
        "requires_human_review": False,
        "routing_decision": "",
        "error": None,
    }

    final_state = compiled_graph.invoke(initial_state)
    return final_state
