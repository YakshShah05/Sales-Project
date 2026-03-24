import os
import time
import httpx
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# Auto-detect: use env var, or sidebar override, or default to localhost
_default_api = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Sales MAS — Prospect Intelligence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.grade-pill {
    display: inline-block;
    padding: 2px 12px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 14px;
}
.grade-A { background: #d1fae5; color: #065f46; }
.grade-B { background: #dbeafe; color: #1e40af; }
.grade-C { background: #fef3c7; color: #92400e; }
.grade-D { background: #fee2e2; color: #991b1b; }
.score-bar-wrap { background: #f1f5f9; border-radius: 8px; height: 8px; }
.score-bar { height: 8px; border-radius: 8px; }
.review-badge { background: #fef9c3; color: #713f12; padding: 2px 8px; border-radius: 8px; font-size: 12px; }
.metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; text-align: center; }
</style>
""", unsafe_allow_html=True)


# ── API helpers ───────────────────────────────────────────────────────────────
def get_api_base() -> str:
    return st.session_state.get("api_base", _default_api)

def api_get(path: str, timeout: int = 10) -> dict | list | None:
    try:
        r = httpx.get(f"{get_api_base()}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error(
            f"Cannot connect to API at `{get_api_base()}`.\n\n"
            "**Fix:** In the sidebar, set the API URL to `http://localhost:8000` "
            "and start backend with:\n"
            "```\n.\\run_api.ps1\n```"
        )
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, data: dict, timeout: int = 60) -> dict | None:
    try:
        r = httpx.post(f"{get_api_base()}{path}", json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error(
            f"Cannot connect to API at `{get_api_base()}`.\n\n"
            "Set the API URL in the sidebar to `http://localhost:8000`."
        )
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def grade_pill(grade: str) -> str:
    return f'<span class="grade-pill grade-{grade}">{grade}</span>'


def score_bar(score: float) -> str:
    color = "#10b981" if score >= 70 else "#3b82f6" if score >= 50 else "#f59e0b" if score >= 30 else "#ef4444"
    return f"""
    <div class="score-bar-wrap">
      <div class="score-bar" style="width:{score}%; background:{color};"></div>
    </div>
    <small style="color:#64748b">{score:.0f} / 100</small>
    """


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Sales MAS")
    st.caption("Multi-Agent Prospect Intelligence")
    st.divider()

    if "api_base" not in st.session_state:
        st.session_state["api_base"] = _default_api

    API_BASE = st.text_input(
        "API URL",
        value=st.session_state["api_base"],
        help="Use http://localhost:8000 for local run",
    )
    st.session_state["api_base"] = API_BASE

    col_test, col_refresh = st.columns(2)
    with col_test:
        if st.button("Test", use_container_width=True):
            try:
                r = httpx.get(f"{API_BASE}/health", timeout=3)
                st.success("Connected ✓")
            except Exception:
                st.error("API unreachable")
    with col_refresh:
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    st.divider()

    page = st.radio(
        "Navigation",
        ["Dashboard", "Score Prospect", "Upload Document", "Human Review", "Feedback", "System Info"],
        label_visibility="collapsed",
    )

    st.divider()
    stats = api_get("/stats") or {}
    st.metric("Total prospects", stats.get("total_prospects", 0))
    st.metric("Avg score", f"{stats.get('avg_score', 0):.1f}")
    st.metric("High priority (≥70)", stats.get("high_priority", 0))
    pending = stats.get("pending_review", 0)
    if pending:
        st.warning(f"⚠️ {pending} pending review")

    st.divider()
    if st.button("🔄 Refresh data"):
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    st.title("🎯 Prospect Intelligence Dashboard")
    st.caption("Ranked prospect queue — built overnight by your multi-agent system")

    prospects = api_get("/prospects?limit=50") or []

    if not prospects:
        st.info("No prospects scored yet. Use 'Score Prospect' to add your first lead.")
        st.stop()

    # KPI row
    scores = [p.get("score", 0) for p in prospects]
    grades = [p.get("grade", "D") for p in prospects]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total prospects", len(prospects))
    k2.metric("Avg score", f"{sum(scores)/len(scores):.1f}" if scores else "—")
    k3.metric("Grade A leads", grades.count("A"))
    k4.metric("Pending review", stats.get("pending_review", 0))

    st.divider()

    # Charts row
    c1, c2 = st.columns(2)

    with c1:
        grade_counts = {g: grades.count(g) for g in ["A", "B", "C", "D"]}
        fig = go.Figure(go.Bar(
            x=list(grade_counts.keys()),
            y=list(grade_counts.values()),
            marker_color=["#10b981", "#3b82f6", "#f59e0b", "#ef4444"],
        ))
        fig.update_layout(
            title="Grade distribution",
            showlegend=False,
            height=240,
            margin=dict(t=40, b=0, l=0, r=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        if scores:
            fig2 = px.histogram(
                x=scores, nbins=10,
                color_discrete_sequence=["#6366f1"],
                labels={"x": "Score", "y": "Count"},
                title="Score distribution",
            )
            fig2.update_layout(height=240, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("Ranked prospect queue")

    for i, p in enumerate(prospects):
        score = p.get("score", 0)
        grade = p.get("grade", "D")
        needs_review = p.get("requires_human_review", False)
        routing = p.get("routing_decision", "")

        with st.container():
            col_rank, col_info, col_score, col_action = st.columns([0.5, 3, 2, 2])

            with col_rank:
                st.markdown(f"**#{i+1}**")

            with col_info:
                review_tag = ' <span class="review-badge">⚠ Review</span>' if needs_review else ""
                st.markdown(
                    f"**{p.get('company_name')}** &nbsp; {grade_pill(grade)}{review_tag}",
                    unsafe_allow_html=True,
                )
                st.caption(f"{p.get('contact_name')} · {p.get('email')}")
                st.caption(f"_{p.get('rationale', '—')}_")

            with col_score:
                st.markdown(score_bar(score), unsafe_allow_html=True)

            with col_action:
                st.caption(f"**Next:** {p.get('recommended_action', '—')}")
                routing_colors = {
                    "rep_notify": "🟢", "human_review": "🟡",
                    "nurture": "🔵", "deprioritize": "⚫"
                }
                st.caption(f"{routing_colors.get(routing, '⚪')} {routing.replace('_', ' ').title()}")

            st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Score Prospect
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Score Prospect":
    st.title("➕ Score a Prospect")
    st.caption("Submit a prospect event — parallel agents will collect signals, LangGraph scores in real-time")

    with st.form("prospect_form"):
        st.subheader("Contact details")
        c1, c2 = st.columns(2)
        company_name = c1.text_input("Company name *", placeholder="Acme Corp")
        contact_name = c2.text_input("Contact name *", placeholder="Jane Smith")
        email = c1.text_input("Email *", placeholder="jane@acme.com")
        event_type = c2.selectbox(
            "Event type *",
            ["new_lead", "email_open", "demo_request", "job_change", "doc_upload"],
        )

        st.subheader("Firmographic data")
        c3, c4 = st.columns(2)
        company_size = c3.selectbox(
            "Company size",
            ["", "1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"],
        )
        industry = c4.selectbox(
            "Industry",
            ["", "SaaS", "FinTech", "HealthTech", "E-commerce", "Enterprise Software",
             "Manufacturing", "Retail", "Education", "Other"],
        )
        revenue = c3.text_input("Annual revenue (approx)", placeholder="$5M–$20M")
        geography = c4.text_input("Geography", placeholder="US, EU, APAC")
        tech_stack_raw = st.text_input(
            "Tech stack (comma-separated)", placeholder="Salesforce, Slack, AWS"
        )
        linkedin_url = st.text_input("LinkedIn URL (optional)")

        submitted = st.form_submit_button("🚀 Score this prospect", use_container_width=True)

    if submitted:
        if not all([company_name, contact_name, email]):
            st.error("Company name, contact name, and email are required.")
        else:
            tech_stack = [t.strip() for t in tech_stack_raw.split(",") if t.strip()] if tech_stack_raw else []

            payload = {
                "event_type": event_type,
                "company_name": company_name,
                "contact_name": contact_name,
                "email": email,
                "company_size": company_size or None,
                "industry": industry or None,
                "revenue": revenue or None,
                "geography": geography or None,
                "tech_stack": tech_stack or None,
                "linkedin_url": linkedin_url or None,
            }

            with st.spinner("Running parallel agents + LangGraph scoring pipeline..."):
                result = api_post("/prospects/score/sync", payload, timeout=90)

            if result:
                st.success("Prospect scored!")
                st.divider()

                m1, m2, m3 = st.columns(3)
                score = result.get("score", 0)
                grade = result.get("grade", "D")
                m1.metric("Score", f"{score:.0f} / 100")
                m2.metric("Grade", grade)
                m3.metric("Routing", result.get("routing_decision", "").replace("_", " ").title())

                st.info(f"**Rationale:** {result.get('rationale')}")
                st.success(f"**Recommended action:** {result.get('recommended_action')}")

                if result.get("requires_human_review"):
                    st.warning("⚠️ This prospect has been flagged for human review (borderline score)")

                with st.expander("Signal details"):
                    signals = result.get("signals", {})
                    for key in ["firmographic", "intent", "engagement", "social", "historical"]:
                        sig = signals.get(key)
                        if sig:
                            st.markdown(f"**{key.title()}** — strength: {sig.get('signal_strength', 0):.0f}")
                            st.json(sig)

                with st.expander("RAG context used"):
                    st.text(result.get("rag_context", "No context retrieved"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Upload Document
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Upload Document":
    st.title("📄 Upload Document")
    st.caption("Upload docs for RAG ingestion — text files go to the text pipeline, images/scanned PDFs go through Tesseract OCR")

    st.info("""
    **Dual-modal RAG pipeline:**
    - `.txt`, `.json`, `.csv`, `.md`, text-based `.pdf` → **Text pipeline** (direct embedding)
    - `.jpg`, `.png`, `.bmp`, scanned `.pdf` → **OCR pipeline** (Tesseract → embedding)
    - Both stores are queried at scoring time for maximum context coverage
    """)

    prospects = api_get("/prospects") or []
    prospect_options = {
        f"{p.get('company_name')} — {p.get('contact_name')}": p.get("prospect_id")
        for p in prospects
    }

    with st.form("upload_form"):
        if prospect_options:
            selected_label = st.selectbox("Link to prospect", list(prospect_options.keys()))
            prospect_id = prospect_options[selected_label]
        else:
            prospect_id = st.text_input("Prospect ID (UUID)", placeholder="Score a prospect first, then upload docs")

        uploaded_file = st.file_uploader(
            "Choose file",
            type=["txt", "pdf", "png", "jpg", "jpeg", "bmp", "json", "csv", "md"],
        )
        upload_submitted = st.form_submit_button("📤 Upload & Index", use_container_width=True)

    if upload_submitted and uploaded_file and prospect_id:
        with st.spinner("Indexing document..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"prospect_id": prospect_id}
            try:
                r = httpx.post(
                    f"{get_api_base()}/documents/upload",
                    files=files,
                    data=data,
                    timeout=60,
                )
                r.raise_for_status()
                result = r.json()

                st.success(f"Document indexed via **{result.get('pipeline', '?').upper()} pipeline**")
                st.metric("Chunks indexed", result.get("chunks_indexed", 0))

                if result.get("ocr_preview"):
                    with st.expander("OCR text preview"):
                        st.text(result["ocr_preview"])

            except Exception as e:
                st.error(f"Upload failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Human Review
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Human Review":
    st.title("👤 Human Review Queue")
    st.caption("Borderline prospects (score 55–65) flagged for manual decision before routing")

    queue = api_get("/review/queue") or []

    if not queue:
        st.success("No prospects pending review.")
        st.stop()

    st.warning(f"{len(queue)} prospect(s) awaiting human decision")

    for p in queue:
        with st.expander(
            f"**{p.get('company_name')}** — Score: {p.get('score', 0):.0f} | {p.get('contact_name')}",
            expanded=True,
        ):
            c1, c2 = st.columns(2)
            c1.metric("Score", f"{p.get('score', 0):.0f}")
            c2.metric("Grade", p.get("grade", "—"))

            st.info(f"**Rationale:** {p.get('rationale')}")
            st.caption(f"Suggested action: {p.get('recommended_action')}")

            with st.form(f"review_{p['prospect_id']}"):
                approved = st.radio(
                    "Decision",
                    ["Approve → notify rep", "Reject → move to nurture"],
                    key=f"dec_{p['prospect_id']}",
                )
                override_action = st.text_input(
                    "Override recommended action (optional)",
                    key=f"act_{p['prospect_id']}",
                )
                notes = st.text_area("Reviewer notes", key=f"notes_{p['prospect_id']}")
                decide = st.form_submit_button("Submit decision", use_container_width=True)

            if decide:
                decision_payload = {
                    "prospect_id": p["prospect_id"],
                    "approved": approved.startswith("Approve"),
                    "reviewer_notes": notes,
                    "override_action": override_action or None,
                }
                result = api_post("/review/decide", decision_payload)
                if result:
                    st.success(f"Decision recorded → {result.get('routing')}")
                    time.sleep(1)
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Feedback
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Feedback":
    st.title("📊 Deal Outcome Feedback")
    st.caption("Record won/lost/ghosted outcomes to improve future scoring")

    col_form, col_history = st.columns([1, 1])

    with col_form:
        st.subheader("Record outcome")
        prospects = api_get("/prospects") or []
        prospect_map = {
            f"{p.get('company_name')} — {p.get('contact_name')}": p.get("prospect_id")
            for p in prospects
        }

        with st.form("feedback_form"):
            selected = st.selectbox("Select prospect", list(prospect_map.keys()) if prospect_map else ["No prospects yet"])
            outcome = st.selectbox("Outcome", ["won", "lost", "ghosted", "nurturing"])
            notes = st.text_area("Notes", placeholder="Key reason, next steps...")
            fb_submitted = st.form_submit_button("Record feedback", use_container_width=True)

        if fb_submitted and prospect_map:
            pid = prospect_map.get(selected)
            result = api_post("/feedback", {"prospect_id": pid, "outcome": outcome, "notes": notes})
            if result:
                st.success(f"Feedback recorded: {outcome}")

    with col_history:
        st.subheader("Outcome history")
        feedback = api_get("/feedback") or []
        if feedback:
            df = pd.DataFrame(feedback)
            outcome_counts = df["outcome"].value_counts()
            fig = px.pie(
                values=outcome_counts.values,
                names=outcome_counts.index,
                color_discrete_map={
                    "won": "#10b981", "lost": "#ef4444",
                    "ghosted": "#94a3b8", "nurturing": "#3b82f6"
                },
                title="Outcome breakdown",
            )
            fig.update_layout(height=280, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df[["outcome", "notes"]].tail(10), use_container_width=True)
        else:
            st.info("No feedback recorded yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: System Info
# ══════════════════════════════════════════════════════════════════════════════
elif page == "System Info":
    st.title("⚙️ System Info")

    st.subheader("Architecture")
    st.markdown("""
    | Component | Technology |
    |---|---|
    | API | FastAPI (async) |
    | Agent orchestration | LangGraph (4-node graph) |
    | Parallel agents | Celery + Redis (5 agents, concurrent) |
    | Vector store | Chroma (dual: text + OCR collections) |
    | OCR | Tesseract via pytesseract |
    | LLM | Groq — Llama 3 8B |
    | Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
    | Frontend | Streamlit |
    | Monitoring | Flower (port 5555) |
    """)

    st.subheader("LangGraph nodes")
    st.markdown("""
    ```
    aggregate → rag_enrich → score → route
                                       ├── rep_notify   (score ≥ 70)
                                       ├── human_review (score 55–65)
                                       ├── nurture      (score 40–69)
                                       └── deprioritize (score < 40)
    ```
    """)

    st.subheader("Celery signal agents (parallel)")
    st.markdown("""
    All 5 agents fire simultaneously via `celery.group()`:
    - `collect_firmographic_signals` — company size, industry, ICP fit
    - `collect_intent_signals` — third-party buying intent
    - `collect_engagement_signals` — email opens, web visits, event type
    - `collect_social_signals` — LinkedIn hiring, exec changes, funding
    - `collect_historical_signals` — CRM history, past deal stages

    Partial failures are handled gracefully — if one agent fails, others proceed.
    """)

    st.subheader("API health")
    health = api_get("/health")
    if health:
        st.success(f"API online — {health.get('timestamp')}")
    else:
        st.error("API unreachable")

    st.caption("Flower task monitor: http://localhost:5555")
    st.caption("API docs (Swagger): http://localhost:8000/docs")