from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_SCOPES, INCLUDED_CALENDARS
from gcal.models import CalendarEvent


def _get_credentials() -> Credentials:
    creds = None
    token_path = Path(GOOGLE_TOKEN_PATH)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_PATH, GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def _parse_event(raw: dict) -> CalendarEvent:
    def parse_dt(dt_field: dict) -> datetime:
        if "dateTime" in dt_field:
            return datetime.fromisoformat(dt_field["dateTime"])
        # all-day event — treat as midnight UTC
        return datetime.fromisoformat(dt_field["date"]).replace(tzinfo=timezone.utc)

    attendees = raw.get("attendees", [])
    # exclude the organizer from the attendee count if they're marked as organizer
    non_organizer = [a for a in attendees if not a.get("organizer", False)]

    return CalendarEvent(
        id=raw["id"],
        title=raw.get("summary", "(no title)"),
        description=raw.get("description", ""),
        start=parse_dt(raw["start"]),
        end=parse_dt(raw["end"]),
        attendee_count=len(non_organizer),
        is_recurring="recurringEventId" in raw,
        recurrence=raw.get("recurrence", []),
    )


def list_calendars() -> list[dict]:
    """Return all calendars the user has access to, as {id, summary} dicts."""
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)
    result = service.calendarList().list().execute()
    return [
        {"id": c["id"], "name": c.get("summary", c["id"]), "is_primary": c.get("primary", False)}
        for c in result.get("items", [])
    ]


def list_events(days_ahead: int = 7) -> list[CalendarEvent]:
    """Fetch events from all accessible calendars, merged and sorted by start time."""
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    # Add 1 extra day as a timezone buffer: a user asking for "--days 3" expects
    # to see events through the end of day 3 in their local timezone. Since events
    # are stored with local offsets, an 8pm PDT event on day 3 is 3am UTC on day 4,
    # so we fetch through end-of-day 4 in UTC to avoid cutting off evening events.
    time_max = (now + timedelta(days=days_ahead + 1)).replace(hour=23, minute=59, second=59)

    all_calendars = list_calendars()
    # "primary" in INCLUDED_CALENDARS matches by the special id "primary", not display name
    calendars = [
        c for c in all_calendars
        if c["name"] in INCLUDED_CALENDARS or c["is_primary"]
    ]
    all_events: list[CalendarEvent] = []

    for cal in calendars:
        try:
            result = (
                service.events()
                .list(
                    calendarId=cal["id"],
                    timeMin=now.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            all_events.extend(_parse_event(e) for e in result.get("items", []))
        except Exception:
            # Skip calendars we can't read (e.g. other people's shared calendars)
            pass

    # Re-sort across all calendars by start time
    all_events.sort(key=lambda e: e.start if e.start.tzinfo else e.start.replace(tzinfo=timezone.utc))
    return all_events


def find_free_slot(
    before: datetime,
    duration_hours: float,
    search_from: datetime | None = None,
    pending_busy: list[tuple[datetime, datetime]] | None = None,
) -> datetime | None:
    """
    Find the first free slot of `duration_hours` between `search_from` and `before`,
    within working hours (9am–7pm local time). Returns the slot start, or None if no
    slot is found.

    `pending_busy` is a list of (start, end) intervals for blocks already proposed
    in the current session but not yet written to the calendar — so we don't double-book.
    """
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    start_search = search_from or now
    # Don't search in the past
    if start_search < now:
        start_search = now

    if start_search >= before:
        return None

    # Query freebusy across all included calendars
    all_calendars = list_calendars()
    cal_ids = [
        {"id": c["id"]}
        for c in all_calendars
        if c["name"] in INCLUDED_CALENDARS or c["is_primary"]
    ]

    body = {
        "timeMin": start_search.isoformat(),
        "timeMax": before.isoformat(),
        "items": cal_ids,
    }
    result = service.freebusy().query(body=body).execute()

    # Collect all busy intervals: calendar busy + any blocks already proposed this session
    busy: list[tuple[datetime, datetime]] = list(pending_busy or [])
    for cal_info in result.get("calendars", {}).values():
        for period in cal_info.get("busy", []):
            busy.append((
                datetime.fromisoformat(period["start"]),
                datetime.fromisoformat(period["end"]),
            ))
    busy.sort(key=lambda x: x[0])

    duration = timedelta(hours=duration_hours)
    slot_start = start_search

    # Walk forward in 30-minute steps, skipping busy blocks and outside working hours
    while slot_start + duration <= before:
        local_hour = slot_start.hour  # UTC hour; good enough for approximate working-hours check
        # Skip outside 9am–7pm
        if local_hour < 9 or local_hour + duration_hours > 19:
            # Jump to 9am next day
            next_day_9am = (slot_start + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            slot_start = next_day_9am
            continue

        slot_end = slot_start + duration
        conflict = next(
            (b for b in busy if b[0] < slot_end and b[1] > slot_start), None
        )
        if conflict is None:
            return slot_start
        # Jump past the conflicting busy block
        slot_start = conflict[1]

    return None


def create_tentative_event(
    title: str,
    start: datetime,
    end: datetime,
    description: str = "",
) -> dict:
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    def fmt(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    body = {
        "summary": f"[TENTATIVE] {title}",
        "description": description,
        "start": {"dateTime": fmt(start)},
        "end": {"dateTime": fmt(end)},
        "status": "tentative",
        "transparency": "transparent",
    }

    return service.events().insert(calendarId="primary", body=body).execute()
