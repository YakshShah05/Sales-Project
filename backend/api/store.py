"""
Simple in-memory store for prospects and feedback.
Replace with PostgreSQL in production.
"""
from typing import Optional
from datetime import datetime
import threading

_lock = threading.Lock()
_prospects: dict[str, dict] = {}
_feedback: list[dict] = []
_pending_review: dict[str, dict] = {}


def save_prospect(prospect_id: str, data: dict):
    with _lock:
        _prospects[prospect_id] = {**data, "updated_at": datetime.utcnow().isoformat()}


def get_prospect(prospect_id: str) -> Optional[dict]:
    return _prospects.get(prospect_id)


def list_prospects(limit: int = 50) -> list[dict]:
    with _lock:
        items = list(_prospects.values())
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items[:limit]


def save_feedback(feedback: dict):
    with _lock:
        _feedback.append({**feedback, "recorded_at": datetime.utcnow().isoformat()})


def list_feedback() -> list[dict]:
    return list(_feedback)


def add_to_review_queue(prospect_id: str, data: dict):
    with _lock:
        _pending_review[prospect_id] = data


def get_review_queue() -> list[dict]:
    return list(_pending_review.values())


def resolve_review(prospect_id: str):
    with _lock:
        _pending_review.pop(prospect_id, None)
