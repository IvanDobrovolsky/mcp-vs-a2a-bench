"""StackOverflow API wrapper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

SO_API = "https://api.stackexchange.com/2.3"


async def get_tag_info(tag: str) -> dict:
    """Get tag statistics from StackOverflow."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Get tag info
        tag_resp = await client.get(
            f"{SO_API}/tags/{tag}/info",
            params={"site": "stackoverflow"},
        )
        total_questions = 0
        if tag_resp.status_code == 200:
            items = tag_resp.json().get("items", [])
            if items:
                total_questions = items[0].get("count", 0)

        # Get recent questions (last 30 days) for activity metrics
        from_date = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        questions_resp = await client.get(
            f"{SO_API}/questions",
            params={
                "tagged": tag,
                "site": "stackoverflow",
                "fromdate": from_date,
                "pagesize": 100,
                "order": "desc",
                "sort": "creation",
                "filter": "total",
            },
        )
        questions_last_30d = 0
        if questions_resp.status_code == 200:
            questions_last_30d = questions_resp.json().get("total", 0)

        # Get sample of recent questions for answer metrics
        sample_resp = await client.get(
            f"{SO_API}/questions",
            params={
                "tagged": tag,
                "site": "stackoverflow",
                "pagesize": 50,
                "order": "desc",
                "sort": "creation",
            },
        )
        avg_answer_count = 0.0
        answered_pct = 0.0
        avg_score = 0.0
        if sample_resp.status_code == 200:
            questions = sample_resp.json().get("items", [])
            if questions:
                total_answers = sum(q.get("answer_count", 0) for q in questions)
                avg_answer_count = total_answers / len(questions)
                answered = sum(1 for q in questions if q.get("is_answered", False))
                answered_pct = (answered / len(questions)) * 100
                total_score = sum(q.get("score", 0) for q in questions)
                avg_score = total_score / len(questions)

        return {
            "tag": tag,
            "total_questions": total_questions,
            "questions_last_30d": questions_last_30d,
            "avg_answer_count": round(avg_answer_count, 2),
            "answered_percentage": round(answered_pct, 1),
            "avg_score": round(avg_score, 2),
        }
