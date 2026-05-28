from dataclasses import dataclass
from gcal.models import CalendarEvent


@dataclass
class PipelineContext:
    # All events fetched at the start of the pipeline.
    # Passed to every reasoner so none of them need to re-query the calendar.
    all_events: list[CalendarEvent]
