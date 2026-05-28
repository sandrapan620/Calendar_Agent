from datetime import datetime, timezone

from gcal.models import CalendarEvent
from agent.classifier import EventType
from agent.reasoners.base import BaseReasoner


class MeetingReasoner(BaseReasoner):

    def event_type(self) -> EventType:
        return EventType.MEETING

    def pull_signals(self, event: CalendarEvent, context) -> dict:
        event_start = event.start
        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=timezone.utc)

        now_dt = datetime.now(event_start.tzinfo)
        days_until = max(0, (event_start - now_dt).days)

        # A description longer than 20 chars suggests there's a real agenda
        has_agenda = bool(event.description and len(event.description.strip()) > 20)

        return {
            "days_until_meeting": days_until,
            "duration_minutes": event.duration_minutes,
            "attendee_count": event.attendee_count,
            "has_agenda": has_agenda,
            "is_recurring": event.is_recurring,
        }

    def guidance_prompt(self) -> str:
        return (
            "Guidance for meeting assessment (deviate if you have a reason — explain in reasoning):\n"
            "- Large meetings (5+ attendees) with no agenda typically need more prep → higher effort\n"
            "- 1:1s with an agenda are usually low effort\n"
            "- Recurring meetings are often lower urgency than one-offs\n"
            "- days_until ≤ 1 → typically urgency 3; 2–3 → urgency 2; > 3 → urgency 1\n"
            "- duration ≥ 90 min → typically effort 3; 30–89 min → effort 2; < 30 min → effort 1"
        )
