from datetime import timezone

from gcal.models import CalendarEvent
from agent.classifier import EventType
from agent.reasoners.base import BaseReasoner

# Words that indicate exam weight — checked against the event title
_WEIGHT_KEYWORDS = {
    "final": "final exam",
    "midterm": "midterm",
    "mid-term": "midterm",
    "quiz": "quiz",
    "test": "test",
}

# Words that mark a study session — checked against other events' titles
_STUDY_KEYWORDS = {"study", "review", "revise", "revision", "prep", "practice"}

# Words to strip when extracting the subject from an exam title
_NOISE_WORDS = {
    "exam", "final", "midterm", "mid-term", "quiz", "test",
    "review", "study", "the", "a", "an", "for", "in", "on",
}


def _exam_weight(title: str) -> str:
    lower = title.lower()
    for keyword, label in _WEIGHT_KEYWORDS.items():
        if keyword in lower:
            return label
    return "unknown"


def _extract_subject(title: str) -> list[str]:
    """Return meaningful words from the title after stripping noise words."""
    words = [w.strip("(),:-") for w in title.lower().split()]
    return [w for w in words if w and w not in _NOISE_WORDS and len(w) > 2]


def _is_study_session(event: CalendarEvent, subject_words: list[str]) -> bool:
    """True if this event looks like a study session for the given subject."""
    lower = event.title.lower()
    has_study_keyword = any(kw in lower for kw in _STUDY_KEYWORDS)
    has_subject_overlap = any(word in lower for word in subject_words)
    return has_study_keyword and has_subject_overlap


class ExamReasoner(BaseReasoner):

    def event_type(self) -> EventType:
        return EventType.EXAM

    def pull_signals(self, event: CalendarEvent, context) -> dict:
        now = event.start.tzinfo and event.start or event.start.replace(tzinfo=timezone.utc)
        # Make sure both datetimes are timezone-aware for comparison
        event_start = event.start
        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=timezone.utc)

        from datetime import datetime
        now_dt = datetime.now(event_start.tzinfo)
        days_until = max(0, (event_start - now_dt).days)

        weight = _exam_weight(event.title)
        subject_words = _extract_subject(event.title)

        # Scan all events that happen before this exam for matching study sessions
        study_sessions = [
            e for e in context.all_events
            if e.id != event.id
            and e.start < event_start
            and _is_study_session(e, subject_words)
        ]

        total_study_hours = sum(s.duration_minutes for s in study_sessions) / 60

        # Summarise prep density as a label the LLM can reason about plainly
        n = len(study_sessions)
        h = total_study_hours
        if n == 0:
            prep_density = "none"
        elif n <= 2 and h < 3:
            prep_density = "light"
        elif n <= 5 or h <= 6:
            prep_density = "moderate"
        else:
            prep_density = "solid"

        return {
            "days_until_exam": days_until,
            "exam_weight": weight,
            "subject": " ".join(subject_words) if subject_words else "unknown",
            "study_sessions_logged": n,
            "total_study_hours": round(h, 1),
            "prep_density": prep_density,
        }

    def guidance_prompt(self) -> str:
        return (
            "Guidance for exam assessment (deviate if you have a reason — explain in reasoning):\n"
            "- Finals and midterms generally warrant higher urgency than quizzes\n"
            "- days_until_exam ≤ 2 → typically urgency 3; 3–7 → urgency 2; > 7 → urgency 1\n"
            "- prep_density 'none' with days_until ≤ 7 → typically effort 3\n"
            "- prep_density 'solid' → effort 1 regardless of days_until\n"
            "- Set confidence < 0.6 when the subject is unclear or study sessions couldn't be matched"
        )
