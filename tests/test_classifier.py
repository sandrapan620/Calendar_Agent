import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gcal.models import CalendarEvent
from agent.classifier import classify_all, EventType
from agent.reasoners.base import _RUBRIC


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sample_events.json"


def _load_fixture_events() -> tuple[list[CalendarEvent], list[EventType]]:
    """Load sample_events.json and return (events, expected_types)."""
    raw = json.loads(FIXTURES_PATH.read_text())
    events = []
    expected = []
    for item in raw:
        events.append(CalendarEvent(
            id=item["id"],
            title=item["title"],
            description=item["description"],
            start=datetime.fromisoformat(item["start"]),
            end=datetime.fromisoformat(item["end"]),
        ))
        expected.append(EventType(item["expected_type"]))
    return events, expected


class TestClassifyAll:
    def test_classifies_fixture_events_correctly(self):
        """Each fixture event should classify to its expected EventType."""
        events, expected_types = _load_fixture_events()
        results = classify_all(events)

        assert len(results) == len(events), "Should return one result per event"

        for event, result, expected in zip(events, results, expected_types):
            assert result == expected, (
                f"'{event.title}' classified as {result.value}, expected {expected.value}"
            )

    def test_empty_list_returns_empty(self):
        """classify_all([]) should return [] without making any LLM call."""
        assert classify_all([]) == []


class TestScoreRubric:
    """Pure Python — no LLM calls, always fast."""

    def test_all_nine_combinations_present(self):
        assert len(_RUBRIC) == 9

    @pytest.mark.parametrize("urgency,effort", [
        (u, e) for u in (1, 2, 3) for e in (1, 2, 3)
    ])
    def test_rubric_returns_nonempty_string(self, urgency, effort):
        from agent.reasoners.base import BaseReasoner

        class _StubReasoner(BaseReasoner):
            def pull_signals(self, e, ctx): return {}
            def event_type(self): return EventType.DEFAULT
            def guidance_prompt(self): return ""

        result = _StubReasoner().score_rubric(urgency, effort)
        assert isinstance(result, str) and len(result) > 0

    def test_rubric_clamps_out_of_range(self):
        """score_rubric should clamp values outside 1–3 rather than raising."""
        from agent.reasoners.base import BaseReasoner

        class _StubReasoner(BaseReasoner):
            def pull_signals(self, e, ctx): return {}
            def event_type(self): return EventType.DEFAULT
            def guidance_prompt(self): return ""

        stub = _StubReasoner()
        assert stub.score_rubric(0, 0) == stub.score_rubric(1, 1)
        assert stub.score_rubric(5, 5) == stub.score_rubric(3, 3)
