# Audio_Too Agents

This is the local agent repo for Audio_Too.

The repo contains two separate offline agents:

- `Admin/`: business administration, project tracking, invoices, session prep, and follow-ups.
- `Marketing/`: outreach, lead tracking, campaign planning, offers, and social posts.

Shared business context lives in:

- `Shared/business_profile.md`
- `Shared/examples/`
- `Shared/data/`
- `Shared/exports/`

The optional Python environment lives at:

- `.venv/`

## Friendly Launcher

Use the top-level launcher for everyday work:

```bash
./agent admin email "Ask a client to send stems for a mix."
```

```bash
./agent admin invoice "Client: Jordan 4 hour vocal recording session at 45 per hour."
```

```bash
./agent admin save-invoice "Client: Jordan 4 hour vocal recording session at 45 per hour."
```

```bash
./agent admin new-client "Client: Sarah Contact: sarah@example.com"
```

```bash
./agent marketing outreach "Lead: Jordan Service: Mixing artist with new single"
```

```bash
./agent marketing leads
```

```bash
./agent marketing pipeline
```

```bash
./agent admin export-invoices
```

```bash
./agent admin export-invoices-xlsx
```

```bash
./agent admin update-invoice "id: <id> status: Paid"
```

```bash
./agent marketing export-leads
```

```bash
./agent marketing export-leads-xlsx
```

```bash
./agent marketing update-lead "lead: Jordan status: Warm follow up: Friday"
```

```bash
./agent marketing score-leads
```

```bash
./agent marketing sequence "Lead: Jordan Service: Mixing"
```

```bash
./agent weekly
```

```bash
./agent dashboard
```

```bash
./agent export-workbook
```

You can also let the launcher route a plain-English request:

```bash
./agent ask "draft an invoice for 4 hours at 45 per hour"
```

Torch routing is available as an explicit opt-in:

```bash
./agent torch train
```

```bash
./agent torch ask "draft an invoice for 4 hours at 45 per hour"
```

Run interactive mode:

```bash
./agent
```

## Admin Agent

Run from the repo root:

```bash
.venv/bin/python Admin/main.py email "Ask a client to send stems for a mix."
```

```bash
.venv/bin/python Admin/main.py invoice "Client: Jordan 4 hour vocal recording session at 45 per hour."
```

```bash
.venv/bin/python Admin/main.py new-project "Client: Sarah Project: Demo Master Service: Mastering Deadline: Friday"
```

```bash
.venv/bin/python Admin/main.py list-projects
```

```bash
.venv/bin/python Admin/main.py clients
```

```bash
.venv/bin/python Admin/main.py invoices
```

```bash
.venv/bin/python Admin/main.py export-invoices
```

```bash
.venv/bin/python Admin/main.py export-invoices-xlsx
```

## Marketing Agent

Run from the repo root:

```bash
.venv/bin/python Marketing/main.py outreach "Lead: Jordan Service: Mixing artist with new single"
```

```bash
.venv/bin/python Marketing/main.py post "Service: Mastering for artists"
```

```bash
.venv/bin/python Marketing/main.py new-lead "Lead: Jordan Contact: instagram.com/jordan Service: Mixing Source: Instagram"
```

```bash
.venv/bin/python Marketing/main.py list-leads
```

```bash
.venv/bin/python Marketing/main.py pipeline
```

```bash
.venv/bin/python Marketing/main.py export-leads
```

```bash
.venv/bin/python Marketing/main.py export-leads-xlsx
```

## Optional Torch Classifier

The Admin agent can use the optional local Torch classifier for `auto` routing.

```bash
# From repo root with .venv activated:
python agents/Admin/torch_classifier.py train
```

```bash
.venv/bin/python Admin/main.py auto "Can you draft an invoice for 4 hours at 45 per hour?" --torch
```
