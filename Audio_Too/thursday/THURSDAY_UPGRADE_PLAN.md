# Thursday Upgrade Plan v2 — From Smart Router to Jarvis-Class Orchestrator

## Executive Summary

Thursday started as a keyword-scoring request router. Phase 1-4 delivered a fully realized orchestrator: persistent session memory (session_manager.py), intent classification (intent.py), unified API client (client.py), declarative service registry (registry.py), entity resolution (resolver.py), proactive monitoring (monitor.py), response formatting (formatter.py), error recovery (errors.py), and full integration across AudioGen, Mix Review, Creative Lab, Portfolio, and Dashboard (phase3_handlers.py).

**All 12 tests pass.** The foundation is solid.

This v2 plan elevates Thursday from a reactive orchestrator into a truly proactive, ambient, Jarvis-class intelligence — always listening, always learning, always anticipating. You talk to it like a person; it knows your business, your habits, your projects, and your goals.

## ✅ CURRENT STATUS: Phases 1-4 COMPLETE

All files implemented and tested:

```
Thursday/
  ├── session_manager.py    ✅ Session CRUD + context management
  ├── intent.py             ✅ Intent classification (10 categories) + entity extraction
  ├── client.py             ✅ Unified API client + APIClient facade class
  ├── registry.py           ✅ Declarative service definitions (~30+ services)
  ├── resolver.py           ✅ Context-aware pronoun/entity resolution
  ├── monitor.py            ✅ Proactive monitoring + alert generation
  ├── formatter.py          ✅ Response formatting + follow-up suggestions
  ├── errors.py             ✅ Error types + recovery strategies
  ├── phase3_handlers.py    ✅ AudioGen, Mix Review, Creative Lab, Portfolio, Dashboard
  ├── bridge.py             ✅ HTTP API for Website integration
  ├── orchestrator.py       ✅ Full routing engine v2
  ├── main.py               ✅ CLI with --session, --new-session, --list-sessions
  ├── __init__.py           ✅ Updated docstring
  ├── changelog.md          ✅ Version history
  ├── alerts/               ✅ Alert storage directory
  └── sessions/             ✅ Session storage directory
```


---

## 🚀 Phase 5: True Jarvis-Class Orchestrator (Ambient Intelligence)

### 5.1 Voice & Natural Interaction Layer

**Goal:** Thursday becomes an always-listening, always-ready assistant you can talk to naturally — not just a CLI or chat widget.

#### 5.1.1 Voice Input / Speech-to-Text
- Integrate a lightweight STT engine (e.g., Whisper.cpp, macOS `say` + `rec`, or local Whisper)
- Create `Thursday/voice.py`:
  ```python
  def listen(wake_word: str = "thursday") -> str:
      """Listen for wake word, then transcribe next utterance."""
  def transcribe(audio_path: str) -> str:
      """Convert audio file to text."""
  ```
- CLI flag: `./audio-too thursday --voice` — enters voice-listening mode
- Hotkey activation: configurable system-wide shortcut to start transcribing

#### 5.1.2 Voice Output / Text-to-Speech
- Integrate macOS `say` command or a local TTS engine
- Create `Thursday/voice_output.py`:
  ```python
  def speak(text: str, voice: str = "Samantha") -> None:
      """Read Thursday's response aloud."""
  ```
- Auto-speak for alerts and brief responses; silent for longer reports
- Configurable on/off via `--silent` flag or session preference

#### 5.1.3 Wake Word + Continuous Listening Mode
- Background daemon that listens for "Hey Thursday" / "Thursday"
- On wake word: capture utterance, process, speak response, return to listening
- Desktop notification when Thursday proactively detects something urgent (alerts)

#### 5.1.4 Multi-Channel Interface
- **CLI** (existing) — `./audio-too thursday "..."` ✅
- **Web Chat** (existing) — `/thursday` page ✅
- **Hub Widget** (existing) — embedded on `/hub` ✅
- **macOS Menu Bar** — lightweight dropdown with input field + last response
- **iOS/Shortcuts** — Siri Shortcut that POSTs to `bridge.py` API
- **Slack Bot** — receive messages in a DM or channel, respond in-thread
- **REST API** (existing bridge.py) ✅ — extend for webhook support


---

### 5.2 Calendar & Time Intelligence

**Problem:** Thursday has no concept of time, dates, or scheduling.

**Solution:** Add a time-awareness layer that understands:
- "What's on my calendar today?"
- "Remind me Thursday at 3pm to send Jordan the stems"
- "Schedule a session with Sarah next Tuesday at 2pm"
- "What does my week look like?"
- "Move Jordan's session to Friday"

#### 5.2.1 Built-in Time Engine
Create `Thursday/calendar.py`:
```python
def parse_datetime(text: str) -> dict:
    """Parse natural datetime from text. Returns {datetime, is_recurring, is_relative, ...}"""

def schedule_reminder(session: dict, text: str, when: str) -> dict:
    """Create a reminder/follow-up record."""

def agenda_for_day(date: str = "today") -> str:
    """Get sessions, reminders, follow-ups for a given day."""

def agenda_for_week(start_date: str = None) -> str:
    """Get weekly agenda grouped by day."""
```

#### 5.2.2 Calendar Integration
- **macOS Calendar** — read/write via AppleScript or EventKit
- **Local agenda** — store in existing `followups` table + new `reminders` table
- **Daily briefing** — auto-fire on first interaction of the day:
  ```
  "Good morning, Jack. Here's your day:
   - Session with Jordan at 2pm
   - Invoice #INV-004 is 3 days overdue
   - Lead 'Sarah from Instagram' needs follow-up (5 days stale)
   - Render job 'joyful-loop' completed overnight
  Ready when you are."
  ```


---

### 5.3 Macros & Custom Automations (Scripting Layer)

**Problem:** You can't teach Thursday new routines.

**Solution:** A macro/scripting system where you can define custom sequences:

#### 5.3.1 Thursday Macros (YAML Scripts)
Create `Thursday/macros/` directory with YAML-defined macros:

```yaml
# Thursday/macros/morning_briefing.yaml
name: "Morning Briefing"
trigger:
  phrase: "good morning"
  time: "weekdays 9:00"
steps:
  - service: "business_status"
  - service: "reminders"
  - service: "sessions"
  - say: "That's your morning roundup, Jack."
```

```yaml
# Thursday/macros/new_client_onboard.yaml
name: "New Client Onboarding"
trigger:
  phrase: "onboard *"
  requires: ["client_name"]
steps:
  - ask: "What service are they interested in?"
  - service: "admin_agent"  # create client record
  - service: "admin_agent"  # create project
  - service: "marketing_agent"  # draft welcome email
  - say: "Client onboarded. Welcome email drafted for approval."
```

#### 5.3.2 Custom Command Recording
- "Thursday, record macro" → begins recording
- User performs sequence of requests
- "Thursday, stop recording" → saves as new macro
- "Thursday, run my morning routine" → executes saved macro

#### 5.3.3 Cross-Module Workflow Builder
Define complex chains that flow across modules:
```yaml
# Thursday/macros/mix_review_full_pipeline.yaml
name: "Full Mix Review Pipeline"
steps:
  - service: "audio_analysis"  # scan folder
  - service: "kenn_review_handoff"  # ask KENN for fixes
  - service: "mix_review_correction_rack"  # generate Ableton rack
  - ask: "Review complete. Should I draft an email to the client?"
  - if: "yes"
    - service: "admin_agent"  # draft email
    - say: "Email drafted for your review."
```


---

### 5.4 Context-Aware Proactive Suggestions (Friday Mode)

**Problem:** Thursday only acts when spoken to. A true assistant anticipates needs.

**Solution:** Add ambient intelligence that surfaces suggestions based on time, data patterns, and past behavior:

#### 5.4.1 Time-Based Triggers
- **Morning (first use)** — daily briefing with agenda, alerts, weather
- **End of week** — weekly summary with top wins, bottlenecks
- **End of month** — profit report, enquiry trends, service demand
- **After a mix review** — "Want me to ask KENN what to fix first?"
- **After an invoice** — "Should I draft a follow-up reminder?"

#### 5.4.2 Pattern Detection
- "You haven't checked your pipeline in 3 days. Want a quick summary?"
- "You always ask about revenue on Mondays. Here's your P&L."
- "Jordan's session is tomorrow. Need me to prepare the template?"
- "Your AudioGen queue has 2 completed renders you haven't reviewed."

#### 5.4.3 Conditional Branching
When Thursday detects a condition, it can proactively suggest an action:
- **Stale lead detected** → "Lead 'Sarah from Instagram' hasn't been contacted in 10 days. Draft an outreach?"
- **Overdue invoice** → "Invoice for Jordan (£500) is 5 days overdue. Send a reminder?"
- **Audio scan complete** → "Scan of 'ClientMixes/ProjectX' complete. 3 tracks need attention."
- **Render finished** → "Your 'joyful-loop' render is ready. Listen or publish to portfolio?"


---

### 5.5 Memory & Preference System

**Problem:** Thursday treats every session like a new user. It doesn't know your preferences, habits, or personality.

**Solution:** Add long-term user profile + preference memory:

#### 5.5.1 User Profile
Create `Thursday/user_profile.py`:
```python
PROFILE_PATH = "Thursday/user_profile.json"

# Schema:
{
  "user_name": "Jack",
  "preferred_voice": "Samantha",
  "timezone": "Europe/London",
  "business_hours": {"start": "09:00", "end": "18:00"},
  "work_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
  "default_render_emotion": "joy",
  "default_bars": 8,
  "preferred_output": "concise",  # or "detailed"
  "auto_speak": True,
  "daily_briefing": True,
  "weekly_summary_day": "Friday",
  "alert_preferences": {
    "stale_leads": True,
    "overdue_invoices": True,
    "enquiries": True,
    "financial_warnings": True,
    "render_complete": True,
  },
  "frequent_clients": ["Jordan", "Sarah", "Test User"],
  "frequent_services": ["Mixing", "Mastering", "Recording"],
  "shortcuts": {
    "jj": "Jordan",
    "sw": "Sarah Williams",
  }
}
```

#### 5.5.2 Learning Layer
- Track frequency of requests to learn patterns
- "You've asked about Jordan 5 times this week. Want me to create a shortcut?"
- Auto-suggest shortcuts for common queries

#### 5.5.3 Mood & Tone Adaptation
- **"I'm stressed"** → switches to calm, brief responses, offers to reschedule non-urgent items
- **"I'm celebrating"** → upbeat tone, offers to share wins on social
- **"Just checking in"** → concise, no follow-ups
- Tone/mood persists for session or until changed


---

### 5.6 External Integrations

#### 5.6.1 Email Integration
- **Read inbox** — "Check my email" → summaries from last N hours
- **Send via SMTP** (partially exists) — draft → review → send
- **Smart triage** — "Any urgent emails?" → flag based on sender, keywords
- **Compose & send** — "Email Jordan the invoice and say thanks"

#### 5.6.2 Slack / Messaging
- **Slack bot** — Thursday listens in a channel, responds to @Thursday
- **Slack notifications** — push alerts to Slack channel
- **WhatsApp bridge** — for client-facing communication (read-only summaries)

#### 5.6.3 File System Awareness
- **Watch directories** — monitor `ClientMixes/`, `Portfolio/audio/`, `Stems/` for new files
- **Auto-scan** — new audio files auto-trigger analysis
- **Auto-organize** — sort new files into project folders by naming convention

#### 5.6.4 macOS Desktop Integration
- **AppleScript support** — control macOS apps (Calendar, Mail, Reminders, Notes)
- **iMessage** — send/receive texts via Messages app
- **Desktop notifications** — alert popups via `osascript`
- **Clipboard** — copy responses, track clipboard for context
- **Spotlight** — file search via `mdfind`


---

### 5.7 Decision Engine & Smart Routing

**Problem:** Thursday picks the best-matching service but can't reason about ambiguous or compound requests.

**Solution:** Add a lightweight decision engine that can:
- **Split compound requests** — "Invoice Jordan and tell me about Sarah" → two actions
- **Ask clarifying questions** — "Did you mean the client Jordan or the lead Jordan from Instagram?"
- **Confirm before destructive actions** — "Delete this project? It has 3 active invoices."
- **Auto-correct common mistakes** — "Show me Jorden" → "Did you mean Jordan?"

#### 5.7.1 Disambiguation
```python
# Thursday/disambiguator.py
def detect_ambiguity(text: str, intent: Intent, context: dict) -> Ambiguity | None:
    """Detect ambiguous references and return options."""

def ask_clarification(ambiguity: Ambiguity) -> str:
    """Generate a clarifying question with numbered options."""

def handle_reply(reply: str, pending_action: dict) -> dict:
    """Process the user's response to a clarification."""
```

#### 5.7.2 Compound Request Parser
```python
# Thursday/compound.py
def split_compound_request(text: str) -> list[str]:
    """Split 'invoice Jordan and check pipeline' → ['invoice Jordan', 'check pipeline']"""

def is_compound(text: str) -> bool:
    """Detect conjunctions connecting separate requests."""
```

#### 5.7.3 Confirmation Dialogs
For destructive or costly operations, Thursday requires confirmation:
- "Delete 15 orphaned uploads? (yes/no)"
- "Send all approved drafts? (yes/no)"
- "Generate 4 variations of a full song render? This may take 5-10 minutes."


---

### 5.8 Self-Healing & Diagnostics

**Problem:** When something breaks, Thursday just shows an error.

**Solution:** Add introspection and self-healing capabilities:

#### 5.8.1 System Health Dashboard (internal)
```python
# Thursday/diagnostics.py
def check_all_systems() -> dict:
    """Run health checks on all subsystems. Returns {system: status} dict."""

def diagnose_error(error: str, service: str) -> str:
    """Suggest fixes for common errors."""
```

Checklist:
- ✅ Is the Website server running? (port 8080)
- ✅ Is KENN running? (port 8090)
- ✅ Is the DB accessible? (SQLite file exists)
- ✅ Is the AudioGen environment healthy?
- ✅ Is the audio analysis tool importable?

#### 5.8.2 Automatic Recovery
- "Thursday, fix the website" → restart the server
- "KENN seems down" → Thursday checks, reports status, attempts restart
- "The database is locked" → tries to clear stale locks, suggests backup

#### 5.8.3 Usage Analytics (local only)
- Track: most-used services, busiest days, common errors, average response time
- "What do I ask you most?" → "You ask about Jordan 40% of the time and check pipeline 25%."
- "How can you be more useful?" → identifies underused services and suggests them


---

### 5.9 Thursday's Personality & Character

**Problem:** Thursday speaks like a tool, not a companion.

**Solution:** Give Thursday a defined personality:

#### 5.9.1 Persona
- **Name:** Thursday (named after the day — "the day before the weekend, when you're wrapping up and planning ahead")
- **Tone:** Professional but warm. Concise when busy, detailed when asked.
- **Catchphrases:**
  - "On it." — when starting a task
  - "Done." — task completed
  - "Here's what I found..." — presenting results
  - "I've got a few things to flag." — alerts
  - "What's next?" — after completing a request
- **Personality file:** `Thursday/personality.py` — configurable responses, greetings, sign-offs

#### 5.9.2 Greeting Variations
Based on time of day and context:
- Morning: "Morning, Jack. I've got your day lined up."
- After a gap: "Welcome back. A few things happened while you were away."
- Late night: "Still going? Here's a quick update — let me know if you need anything else."
- Weekend: "Quiet day. I'll keep an eye on things."

#### 5.9.3 Emotional Intelligence
- Detects frustration ("why isn't this working") → apologetic + solution-focused
- Detects urgency ("right now", "immediately") → skips pleasantries, faster verbosity
- Detects celebration ("great news", "we did it") → congratulatory + offer to share


---

### 5.10 Multi-Session & Collaboration

**Problem:** Thursday only talks to one user at a time.

**Solution:** Support multiple simultaneous sessions and user switching:

#### 5.10.1 User Profiles
- Store per-user preferences, history, and context
- Switch with `--user Jack` or "I'm Jack"
- Different alert configurations per user

#### 5.10.2 Shared Context
- "What did Jack ask earlier?" — cross-user context lookup
- "Jordan called while you were away" — log messages from other channels


---

## Phase 6: Learning & Personalization (Long-Term)

### 6.1 Feedback Loop
- **Thumbs up/down** on responses (stored in session)
- "Was that helpful?" — occasional check-in
- Auto-retrain intent patterns based on corrections

### 6.2 Habit Learning
- Track: time of day, frequency, most-used modules, typical sequences
- "I notice you always check pipeline after adding a lead. Want me to auto-run that?"
- Learn preferred response length, verbosity, emoji usage

### 6.3 Recipe Library (Community Macros)
- Shareable macro definitions
- Import/export macros as YAML files
- Community templates: "client onboarding", "weekly admin", "project kick-off"


---

## Phase 7: Advanced Orchestration (AI Core)

### 7.1 LLM-Powered Routing (Optional)
- For ambiguous or unknown requests, use an LLM (local or API) to classify intent
- Fallback chain: regex → ML classifier → LLM
- LLM can also extract entities more reliably than regex

### 7.2 Memory-Augmented Context
- Long-term memory store (vector DB or simple JSON) that persists across sessions
- "What did Jordan and I discuss last month?" — retrieves past conversation summaries
- Automatic summarization of long sessions into memory entries

### 7.3 Autonomous Task Execution
- "Keep checking for new enquiries every hour and alert me" — schedule a recurring task
- "Monitor this project and tell me when the deadline is approaching" — watch + notify
- "After the audio scan completes, ask KENN for fixes, then draft an email to the client" — autonomous chain


---

## File Change Summary (Phase 5+)

```
NEW:  Thursday/voice.py                  — Speech-to-text (wake word + transcription)
NEW:  Thursday/voice_output.py           — Text-to-speech output
NEW:  Thursday/calendar.py               — Time/datetime parsing + scheduling
NEW:  Thursday/compound.py               — Compound request splitting
NEW:  Thursday/disambiguator.py          — Ambiguity detection + clarification
NEW:  Thursday/diagnostics.py            — System health + self-healing
NEW:  Thursday/personality.py            — Personality config + greeting templates
NEW:  Thursday/user_profile.py           — Long-term preferences + learning
NEW:  Thursday/macros/                   — Macro definition directory
NEW:  Thursday/macros/morning_briefing.yaml
NEW:  Thursday/macros/new_client_onboard.yaml
NEW:  Thursday/macros/mix_review_full_pipeline.yaml

MOD:  Thursday/orchestrator.py           — Add compound request splitting, clarification flow
MOD:  Thursday/registry.py               — Add macro services, calendar services
MOD:  Thursday/main.py                   — Add --voice, --user, --macro flags
MOD:  Thursday/bridge.py                 — Add user switching, multi-session support
MOD:  Thursday/formatter.py              — Add personality-driven tone adaptation
MOD:  Thursday/client.py                 — Add calendar, diagnostics, file watch methods
MOD:  Thursday/intent.py                 — Add compound intent patterns, time patterns
MOD:  Thursday/session_manager.py        — Add user_id, preferences to session schema
MOD:  Thursday/monitor.py                — Add scheduled reminders, render completion alerts
```


---

## Architecture Diagram v3 (Full Jarvis)

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         INTERACTION LAYER                                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐  ┌───────────┐   │
│  │   CLI    │  │ Web Chat │  │ Hub Widget │  │ Voice  │  │ Slack Bot │   │
│  │ (main.py)│  │(bridge.py)│  │ (JS fetch)│  │(voice.py)│ (webhook) │   │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └───┬────┘  └─────┬─────┘   │
│       └──────────────┴──────────────┴─────────────┴──────────────┘       │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────────────┐
│                       ORCHESTRATION CORE                                  │
│                                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────────┐             │
│  │  main.py     │───▶│ orchestrator │───▶│  compound.py    │             │
│  │  (entry)     │    │  (routing)   │    │  (split + queue)│             │
│  └──────────────┘    └──────┬───────┘    └─────────────────┘             │
│                              │                                            │
│         ┌────────────────────┼────────────────────┐                      │
│         ▼                    ▼                    ▼                      │
│  ┌───────────┐      ┌──────────────┐    ┌───────────────┐                │
│  │ intent.py │      │  resolver.py │    │  registry.py  │                │
│  │ classify  │      │  resolve     │    │  score+select │                │
│  └───────────┘      └──────────────┘    └──────┬────────┘                │
│                                                 │                         │
│         ┌───────────────────────────────────────┼───────────────┐        │
│         ▼           ▼           ▼               ▼               ▼        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐ │
│  │session_mgr│ │monitor  │ │formatter │ │disambiguator│ │ diagnostics  │ │
│  │persist   │ │alerts   │ │response  │ │clarify     │ │health+heal   │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ └──────────────┘ │
│                                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐               │
│  │ personality  │  │ user_profile │  │ calendar.py      │               │
│  │ (tone/traits)│  │ (prefs/learn)│  │ (time/schedule)  │               │
│  └──────────────┘  └──────────────┘  └──────────────────┘               │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Macros Engine (macros/ directory — YAML-defined workflows)       │  │
│  │  "record macro" → "run my morning routine" → "export macro"      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────────────┐
│                         SERVICE LAYER                                     │
│                                                                           │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐    │
│  │  client  │ │ Abington │ │ Agents  │ │ Creative │ │ AudioGen     │    │
│  │  API     │ │ Bridge   │ │(Admin,  │ │ Lab      │ │ (generate,   │    │
│  │  (data,  │ │ (KENN,   │ │ Market, │ │ (repairs,│ │  render,     │    │
│  │  finance)│ │  Notes)  │ │ Research)│ │  events) │ │  status)     │    │
│  └──────────┘ └──────────┘ └─────────┘ └──────────┘ └──────────────┘    │
│                                                                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────────────┐     │
│  │ Audio        │ │ Portfolio    │ │ Calendar │ │ Voice I/O       │     │
│  │ Analysis     │ │ (list,       │ │ (schedule│ │ (STT + TTS)     │     │
│  │ (scan,review)│ │  publish)    │ │  events) │ │                 │     │
│  └──────────────┘ └──────────────┘ └──────────┘ └─────────────────┘     │
└───────────────────────────────────────────────────────────────────────────┘
```


---

## Priority Order for Phase 5+

| Priority | Feature | Why |
|----------|---------|-----|
| P0 | **Calendar & Time Intelligence** | Foundation for scheduling, reminders, daily briefings |
| P0 | **Decision Engine (Compound + Disambiguation)** | Makes Thursday smarter about complex requests |
| P0 | **User Profile + Preferences** | Personalization foundation |
| P1 | **Macros / Custom Automations** | Lets you teach Thursday new tricks |
| P1 | **Personality & Tone** | Makes Thursday feel like a companion, not a tool |
| P1 | **Context-Aware Proactive Suggestions** | The "Friday mode" that anticipates needs |
| P2 | **Voice Input / STT** | Hands-free operation |
| P2 | **Voice Output / TTS** | True assistant feel |
| P2 | **macOS Desktop Integration** | Calendar, Mail, Notifications, iMessage |
| P2 | **Diagnostics & Self-Healing** | Thursday fixes itself |
| P3 | **External Integrations (Slack, Email)** | Multi-platform presence |
| P3 | **Multi-Session / Collaboration** | Team support |
| P4 | **LLM-Powered Routing** | Smarter fallback for unknowns |
| P4 | **Autonomous Task Execution** | "Watch this and alert me" |

---

## Success Criteria v3 (Extended)

1. **Voice interaction** — "Hey Thursday, how's business?" → hears, processes, speaks back
2. **Compound requests** — "Invoice Jordan and tell me about Sarah" → both actions executed
3. **Clarification** — "Show me Jordan" "Which one? 1. Client 2. Lead from Instagram"
4. **Calendar awareness** — "What's on Thursday?" → knows the date, returns schedule
5. **Proactive suggestions** — After a scan: "Want me to ask KENN about the results?"
6. **Macros** — "Run my morning briefing" → executes custom sequence
7. **Personality** — Tone adapts to time of day, user mood, context
8. **User profile** — Preferences persist across sessions
9. **Self-healing** — "The server seems down" → checks and reports
10. **External integrations** — Slack, macOS Calendar, email read/send

---

## Milestones v3

| Milestone | Deliverables |
|-----------|--------------|
| M1: Calendar & Time | `calendar.py`, scheduling, daily briefing, reminders |
| M2: Decision Engine | `compound.py`, `disambiguator.py`, clarification flow |
| M3: User Profile | `user_profile.py`, preferences, learning layer |
| M4: Macros System | `macros/`, recording engine, YAML runner |
| M5: Personality | `personality.py`, greeting variations, tone adaptation |
| M6: Proactive Mode | Ambient suggestions, time-based triggers, pattern detection |
| M7: Voice I/O | `voice.py`, `voice_output.py`, wake word, continuous mode |
| M8: macOS Desktop | AppleScript, calendar, notifications, iMessage, clipboard |
| M9: Diagnostics | `diagnostics.py`, health checks, auto-recovery |
| M10: External Integrations | Slack bot, email reading, multi-channel presence |
