from celery import group, chord
from tasks.celery_app import celery_app
from tasks.signal_tasks import (
    collect_firmographic_signals,
    collect_intent_signals,
    collect_engagement_signals,
    collect_social_signals,
    collect_historical_signals,
)


@celery_app.task(bind=True)
def aggregate_signals_task(self, results: list) -> dict:
    """Aggregate results from all parallel signal agents."""
    aggregated = {
        "firmographic": None,
        "intent": None,
        "engagement": None,
        "social": None,
        "historical": None,
    }

    keys = ["firmographic", "intent", "engagement", "social", "historical"]
    for i, result in enumerate(results):
        if result and not isinstance(result, Exception):
            aggregated[keys[i]] = result

    strengths = [
        v.get("signal_strength", 0)
        for v in aggregated.values()
        if v and isinstance(v, dict)
    ]
    aggregated["composite_signal_score"] = sum(strengths) / len(strengths) if strengths else 0

    return aggregated


@celery_app.task(bind=True)
def run_prospect_pipeline(self, prospect_data: dict) -> dict:
    """
    Main pipeline task. Fires all signal agents in parallel using Celery group.
    Uses chord to aggregate results once all tasks complete.
    Partial failures are handled gracefully — failed tasks return None.
    """
    task_group = group(
        collect_firmographic_signals.s(prospect_data),
        collect_intent_signals.s(prospect_data),
        collect_engagement_signals.s(prospect_data),
        collect_social_signals.s(prospect_data),
        collect_historical_signals.s(prospect_data),
    )

    pipeline = chord(task_group)(aggregate_signals_task.s())
    return {"chord_id": pipeline.id, "prospect_id": prospect_data.get("prospect_id")}
