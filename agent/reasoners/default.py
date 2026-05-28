from datetime import datetime, timezone

from gcal.models import CalendarEvent
from agent.classifier import EventType
from agent.reasoners.base import BaseReasoner


class DefaultReasoner(BaseReasoner):

    def event_type(self) -> EventType:
        return EventType.DEFAULT

    def pull_signals(self, event: CalendarEvent, context) -> dict:
        event_start = event.start
        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=timezone.utc)

        now_dt = datetime.now(event_start.tzinfo)
        days_until = max(0, (event_start - now_dt).days)

        return {
            "days_until": days_until,
            "duration_minutes": event.duration_minutes,
            "has_description": bool(event.description and event.description.strip()),
        }

    def guidance_prompt(self) -> str:
        return (
            "Guidance for general event assessment (deviate if you have a reason — explain in reasoning):\n"
            "- days_until ≤ 1 → typically urgency 3; 2–4 → urgency 2; > 4 → urgency 1\n"
            "- duration ≥ 120 min → typically effort 3; 30–119 min → effort 2; < 30 min → effort 1\n"
            "- Use the event title and description to judge if any special prep is needed"
        )
