from abc import ABC, abstractmethod

from gcal.models import CalendarEvent
from llm.client import complete
from agent.classifier import EventType
from output.schema import ReasonerOutput


# The tool definition we send to Claude when asking it to assess an event.
# Claude must call this tool — it can't reply in free text — which guarantees
# we always get urgency, effort, confidence, and reasoning back as structured data.
_ASSESS_TOOL = {
    "name": "assess_event",
    "description": "Assess the urgency and effort required for a calendar event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "urgency": {
                "type": "integer",
                "description": "How time-sensitive is this event? 1=low, 2=medium, 3=high",
                "enum": [1, 2, 3],
            },
            "effort": {
                "type": "integer",
                "description": "How much preparation/work does this event require? 1=low, 2=medium, 3=high",
                "enum": [1, 2, 3],
            },
            "confidence": {
                "type": "number",
                "description": "How confident are you in this assessment? 0.0 to 1.0",
            },
            "reasoning": {
                "type": "string",
                "description": "A concise explanation of your urgency and effort scores.",
            },
            "suggested_action": {
                "type": "string",
                "description": "One concrete action the user should take, e.g. 'Block 2h prep on Monday'",
            },
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Any caveats or uncertainties about this assessment.",
            },
        },
        "required": ["urgency", "effort", "confidence", "reasoning", "suggested_action", "caveats"],
    },
}

# The 3×3 recommendation matrix. Given urgency and effort scores from the LLM,
# this maps them to a plain-English recommendation string.
_RUBRIC: dict[tuple[int, int], str] = {
    (3, 3): "Block time immediately — high stakes, significant prep needed",
    (3, 2): "Prioritize today — urgent with moderate prep",
    (3, 1): "Handle today — urgent but quick",
    (2, 3): "Schedule a dedicated prep block this week",
    (2, 2): "Slot prep time in the next 2 days",
    (2, 1): "Add to today's task list",
    (1, 3): "Plan ahead — low urgency but heavy lift",
    (1, 2): "Batch with similar tasks this week",
    (1, 1): "No action needed",
}


class BaseReasoner(ABC):

    @abstractmethod
    def pull_signals(self, event: CalendarEvent, context) -> dict:
        """
        Extract raw, factual signals about this event from the context.
        No LLM calls here — pure Python logic only.
        Returns a dict of signal name → value that gets sent to the LLM.
        """

    @abstractmethod
    def event_type(self) -> EventType:
        """Which EventType this reasoner handles."""

    @abstractmethod
    def guidance_prompt(self) -> str:
        """
        Type-specific guidance thresholds to include in the LLM prompt.
        Tells the model what the signals mean in plain language.
        """

    def run(self, event: CalendarEvent, context) -> ReasonerOutput:
        signals = self.pull_signals(event, context)

        # Format signals as a readable list for the prompt
        signals_text = "\n".join(f"  - {k}: {v}" for k, v in signals.items())

        prompt = (
            f"You are assessing a calendar event to help the user prioritise their time.\n\n"
            f"Event: {event.title}\n"
            f"Description: {event.description or '(none)'}\n\n"
            f"Signals extracted from the calendar:\n{signals_text}\n\n"
            f"{self.guidance_prompt()}\n\n"
            f"Use the assess_event tool to return your assessment. "
            f"You may deviate from the guidance if you have a good reason — explain it in reasoning."
        )

        response = complete(
            messages=[{"role": "user", "content": prompt}],
            tools=[_ASSESS_TOOL],
        )

        # Extract the tool_use block from Claude's response
        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "assess_event":
                tool_input = block.input
                break

        # Fallback if the model didn't call the tool (shouldn't happen, but be safe)
        if tool_input is None:
            tool_input = {
                "urgency": 1, "effort": 1, "confidence": 0.0,
                "reasoning": "Assessment unavailable.",
                "suggested_action": "Review manually.",
                "caveats": ["LLM did not return a structured assessment."],
            }

        urgency = int(tool_input["urgency"])
        effort = int(tool_input["effort"])

        return ReasonerOutput(
            event_id=event.id,
            event_title=event.title,
            event_type=self.event_type(),
            urgency=urgency,
            effort=effort,
            confidence=float(tool_input["confidence"]),
            reasoning=tool_input["reasoning"],
            recommendation=self.score_rubric(urgency, effort),
            suggested_action=tool_input["suggested_action"],
            caveats=tool_input.get("caveats", []),
        )

    def score_rubric(self, urgency: int, effort: int) -> str:
        """Map LLM-produced urgency + effort scores to a recommendation string."""
        # Clamp to valid range in case the LLM somehow returns out-of-range values
        u = max(1, min(3, urgency))
        e = max(1, min(3, effort))
        return _RUBRIC[(u, e)]
