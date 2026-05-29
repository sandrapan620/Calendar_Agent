# Calendar Agent

A reasoning agent that fetches your Google Calendar events, classifies each one, and produces structured recommendations — then offers to schedule tentative prep blocks in your calendar automatically.

---

## What it does

```
Google Calendar → classify all events (one LLM call)
                → route each to a type-specific reasoner
                → LLM produces urgency × effort scores + reasoning
                → render Rich table
                → find free slots → suggest [TENTATIVE] prep blocks one at a time
```

Each event gets a `ReasonerOutput` with:
- **urgency** (1–3) and **effort** (1–3) scored by the LLM
- **recommendation** mapped from the urgency × effort rubric
- **confidence** (0–1) and **reasoning** in plain language
- **suggested action** + optional tentative calendar block

---

## Setup

### Prerequisites

- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com/)
- A Google Cloud project with the **Google Calendar API** enabled

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/Calendar_Agent.git
cd Calendar_Agent
pip install -r requirements.txt
```

### 2. Anthropic API key

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Google Calendar credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Library**
2. Enable the **Google Calendar API**
3. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Application type: **Desktop app**
5. Download the JSON file and save it as `credentials.json` in the project root

On first run, a browser window will open for OAuth consent. The token is cached to `token.json` and reused on subsequent runs.

### 4. Choose your calendars

Edit `config.py` to select which calendars to include:

```python
INCLUDED_CALENDARS = {"primary", "classes", "clubs/activities"}
```

Use the exact calendar names as they appear in Google Calendar. Your primary calendar is always included via the `is_primary` flag regardless of its display name.

---

## Usage

```bash
python main.py batch --days 14
```

**What happens:**

1. Fetches events from your selected calendars for the next N days
2. Classifies all events in one batched LLM call (EXAM / MEETING / DEFAULT)
3. Reasons about each event individually — urgency, effort, confidence, and a suggested action
4. Renders a colour-coded table (urgency: green/yellow/red)
5. For high-urgency events that need prep, finds free slots in your calendar and suggests tentative blocks one at a time — you confirm or skip each one

**Options:**

```bash
python main.py batch --days 7     # default: 7 days ahead
python main.py batch --days 30    # look further ahead
```

---

## Project structure

```
Calendar_Agent/
├── main.py                    # CLI entry point — batch command
├── config.py                  # API keys, model, included calendars
│
├── gcal/
│   ├── client.py              # Google Calendar auth, list_events(), find_free_slot(), create_tentative_event()
│   └── models.py              # CalendarEvent dataclass
│
├── llm/
│   └── client.py              # Single LLM seam — all Anthropic SDK calls go through here
│
├── agent/
│   ├── classifier.py          # Batched event classification (one LLM call for all events)
│   ├── pipeline.py            # PipelineContext dataclass
│   ├── router.py              # EventType → Reasoner dispatch
│   └── reasoners/
│       ├── base.py            # Abstract reasoner + assess_event tool + score_rubric()
│       ├── exam.py            # ExamReasoner — detects exam weight, subject, study sessions
│       ├── meeting.py         # MeetingReasoner — attendees, agenda, duration, recurrence
│       └── default.py         # DefaultReasoner — fallback for all other events
│
├── output/
│   ├── schema.py              # ReasonerOutput dataclass
│   └── renderer.py            # Rich table output (storage seam — add S3 here later)
│
├── tests/
│   ├── test_classifier.py     # Classifier + score_rubric unit tests
│   └── fixtures/
│       └── sample_events.json
│
├── requirements.txt
├── pytest.ini
└── .env.example
```

---

## How it works

### LLM seam
All Anthropic SDK calls go through `llm/client.py → complete()`. Swapping to AWS Bedrock later is a one-file change here.

### Batched classifier
`classify_all()` sends all event titles/descriptions to Claude in a single call and gets back a JSON array of `EXAM | MEETING | DEFAULT` labels. One API call regardless of how many events.

### Type-specific reasoners
Each reasoner's `pull_signals()` extracts raw facts in pure Python (no LLM) — days until event, prep sessions logged, attendee count, etc. These are passed to Claude via the `assess_event` tool, which returns `urgency`, `effort`, `confidence`, and `reasoning` as structured output.

The prompt includes guidance thresholds ("finals within 3 days → typically urgency 3") but explicitly allows the model to deviate with an explanation. This is why confidence is meaningful — the LLM emits it directly based on how clear the signals are.

### Urgency × effort rubric
`score_rubric(urgency, effort)` in `base.py` maps the 3×3 grid to plain-English recommendations:

| | Effort 1 | Effort 2 | Effort 3 |
|---|---|---|---|
| **Urgency 3** | Handle today — urgent but quick | Prioritize today — urgent with moderate prep | Block time immediately |
| **Urgency 2** | Add to today's task list | Slot prep time in the next 2 days | Schedule a dedicated prep block this week |
| **Urgency 1** | No action needed | Batch with similar tasks this week | Plan ahead — low urgency but heavy lift |

### Tentative event creation
When the agent suggests a prep block, it:
1. Queries your freebusy calendar to find an open slot before the event deadline
2. Respects your Google Calendar timezone (auto-detected) and only suggests times between 8am–10pm
3. Creates the event with `status=tentative` and `transparency=transparent` — it shows in your calendar but doesn't block your time for others and is visually marked as tentative

> **Note:** Google Calendar does not support creating an event where the organizer is in `needsAction` state — the organizer is always auto-accepted. The `[TENTATIVE]` prefix in the title and `status=tentative` on the event body are the closest equivalent.

---

## Running tests

```bash
pytest tests/
```

13 tests covering:
- Classifier output for all three event types (makes one real LLM call)
- Empty-list edge case
- All 9 urgency × effort rubric combinations
- Rubric clamping (out-of-range scores)

---

## Planned next work

- **Deadline reasoner** — fourth event type, same pattern as exam/meeting/default
- **Interactive chat mode** — ask about specific events instead of batch processing all
- **AWS story** — swap `llm/client.py` for Bedrock, add `storage/s3_notes.py` for persisting reasoning
- **LLM eval harness** — score reasoning quality against labelled fixture events (urgency/effort scores from LLM can't be unit-tested for exact values today)
- **Streamlit UI** — visual alternative to the CLI table

---

## What's not committed

`.env`, `credentials.json`, and `token.json` are in `.gitignore` and will never be committed.

