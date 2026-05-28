import json
from enum import Enum

from gcal.models import CalendarEvent
from llm.client import complete


class EventType(str, Enum):
    EXAM = "EXAM"
    MEETING = "MEETING"
    DEFAULT = "DEFAULT"


_CLASSIFY_TOOL = {
    "name": "classify_events",
    "description": "Classify each calendar event into exactly one of: EXAM, MEETING, or DEFAULT.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "description": "One classification per event, in the same order as the input list.",
                "items": {
                    "type": "string",
                    "enum": ["EXAM", "MEETING", "DEFAULT"],
                },
            }
        },
        "required": ["classifications"],
    },
}


def classify_all(events: list[CalendarEvent]) -> list[EventType]:
    if not events:
        return []

    # Build a numbered list of events to put in the prompt.
    # We only send the title and description — that's all the model needs
    # to decide "is this an exam, a meeting, or something else?"
    event_lines = []
    for i, e in enumerate(events):
        desc = e.description[:200] if e.description else "(no description)"
        event_lines.append(f"{i + 1}. Title: {e.title}\n   Description: {desc}")

    prompt = (
        "Classify each of the following calendar events.\n\n"
        "Rules:\n"
        "- EXAM: any test, exam, quiz, or assessment the user is taking\n"
        "- MEETING: any event with other people (sync, standup, interview, call, etc.)\n"
        "- DEFAULT: everything else (personal tasks, reminders, study blocks, etc.)\n\n"
        "Events:\n" + "\n\n".join(event_lines) + "\n\n"
        "Return exactly one classification per event, in the same order."
    )

    response = complete(
        messages=[{"role": "user", "content": prompt}],
        tools=[_CLASSIFY_TOOL],
    )

    # Walk the response to find the tool_use block.
    # The model is forced to call our tool because we defined it —
    # this gives us a structured list back instead of free text.
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_events":
            raw = block.input.get("classifications", [])
            result = []
            for i, label in enumerate(raw):
                try:
                    result.append(EventType(label))
                except ValueError:
                    # If the model returns something unexpected, default to DEFAULT
                    result.append(EventType.DEFAULT)
            # Pad with DEFAULT if the model returned fewer items than events
            while len(result) < len(events):
                result.append(EventType.DEFAULT)
            return result

    # If for some reason there was no tool_use block at all, default everything
    return [EventType.DEFAULT] * len(events)
