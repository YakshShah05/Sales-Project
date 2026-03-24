import random
import time
from tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, soft_time_limit=30)
def collect_firmographic_signals(self, prospect_data: dict) -> dict:
    """Collect company size, industry, revenue, tech stack signals."""
    try:
        time.sleep(0.3)
        company_size = prospect_data.get("company_size", "unknown")
        industry = prospect_data.get("industry", "unknown")
        revenue = prospect_data.get("revenue", "unknown")
        tech_stack = prospect_data.get("tech_stack", [])

        size_score = {
            "1-10": 20, "11-50": 40, "51-200": 65,
            "201-500": 80, "501-1000": 90, "1000+": 95
        }.get(company_size, 30)

        icp_industries = ["SaaS", "FinTech", "HealthTech", "E-commerce", "Enterprise Software"]
        industry_match = industry in icp_industries

        return {
            "company_size": company_size,
            "industry": industry,
            "revenue": revenue,
            "tech_stack": tech_stack,
            "size_score": size_score,
            "industry_match": industry_match,
            "icp_fit": "high" if (size_score > 60 and industry_match) else "medium" if size_score > 40 else "low",
            "signal_strength": size_score,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(bind=True, max_retries=2, soft_time_limit=30)
def collect_intent_signals(self, prospect_data: dict) -> dict:
    """Collect buying intent signals — third-party data, review activity."""
    try:
        time.sleep(0.4)
        company_name = prospect_data.get("company_name", "")

        intent_score = random.randint(20, 95)
        signals_detected = []

        if intent_score > 70:
            signals_detected.append("Competitor review activity on G2")
        if intent_score > 60:
            signals_detected.append("Pricing page visits detected")
        if intent_score > 50:
            signals_detected.append("Category search activity spiked")

        return {
            "intent_score": intent_score,
            "signals_detected": signals_detected,
            "buying_stage": "evaluation" if intent_score > 70 else "awareness" if intent_score > 40 else "cold",
            "signal_strength": intent_score,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(bind=True, max_retries=2, soft_time_limit=30)
def collect_engagement_signals(self, prospect_data: dict) -> dict:
    """Collect email opens, website visits, demo requests."""
    try:
        time.sleep(0.2)
        event_type = prospect_data.get("event_type", "")

        base_score = 30
        engagement_events = []

        if event_type == "email_open":
            base_score += 25
            engagement_events.append("Email opened")
        if event_type == "demo_request":
            base_score += 50
            engagement_events.append("Demo requested — high intent")
        if event_type == "new_lead":
            base_score += 15
            engagement_events.append("New inbound lead")

        email_opens = random.randint(0, 8)
        website_visits = random.randint(0, 15)
        base_score += min(email_opens * 3, 15) + min(website_visits * 2, 10)

        return {
            "email_opens": email_opens,
            "website_visits": website_visits,
            "engagement_events": engagement_events,
            "recency": "hot" if base_score > 70 else "warm" if base_score > 40 else "cold",
            "signal_strength": min(base_score, 100),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(bind=True, max_retries=2, soft_time_limit=30)
def collect_social_signals(self, prospect_data: dict) -> dict:
    """Collect LinkedIn job changes, exec activity, hiring patterns."""
    try:
        time.sleep(0.5)
        company_name = prospect_data.get("company_name", "")

        hiring_count = random.randint(0, 20)
        exec_changed = random.random() > 0.7
        funding_recent = random.random() > 0.8

        social_score = 20
        signals = []

        if hiring_count > 10:
            social_score += 30
            signals.append(f"Active hiring: {hiring_count} open roles")
        if exec_changed:
            social_score += 25
            signals.append("New executive hire detected — buying window open")
        if funding_recent:
            social_score += 35
            signals.append("Recent funding round — budget available")

        return {
            "hiring_count": hiring_count,
            "exec_change_detected": exec_changed,
            "funding_detected": funding_recent,
            "social_signals": signals,
            "signal_strength": min(social_score, 100),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(bind=True, max_retries=2, soft_time_limit=30)
def collect_historical_signals(self, prospect_data: dict) -> dict:
    """Collect CRM history — past deal stages, lost reasons, prior contact."""
    try:
        time.sleep(0.3)
        email = prospect_data.get("email", "")

        had_prior_contact = random.random() > 0.6
        prior_stage = random.choice(["never_contacted", "demo_done", "proposal_sent", "lost_budget", "lost_timing"])

        history_score = 30
        notes = []

        stage_scores = {
            "never_contacted": 30,
            "demo_done": 55,
            "proposal_sent": 70,
            "lost_budget": 45,
            "lost_timing": 65,
        }

        if had_prior_contact:
            history_score = stage_scores.get(prior_stage, 30)
            notes.append(f"Prior contact history: {prior_stage.replace('_', ' ')}")
            if prior_stage == "lost_timing":
                notes.append("Previously lost due to timing — re-engage now")

        return {
            "had_prior_contact": had_prior_contact,
            "prior_stage": prior_stage if had_prior_contact else None,
            "crm_notes": notes,
            "signal_strength": history_score,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)
