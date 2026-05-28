from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CalendarEvent:
    id: str
    title: str
    description: str
    start: datetime
    end: datetime
    attendee_count: int = 0
    is_recurring: bool = False
    recurrence: list[str] = field(default_factory=list)

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)
