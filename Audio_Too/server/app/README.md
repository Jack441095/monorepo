# Audio_Too Website

This is a local website and backend bridge for Audio_Too.

It serves:

- Public website pages
- Project enquiry form
- Admin dashboard data
- Marketing lead dashboard data

The backend reads and writes the agents' shared JSON data in:

```text
../agents/Shared/data/
```

## Run

```bash
python3 Website/server.py
```

Open:

```text
http://127.0.0.1:8080
```

## API

- `GET /api/summary`
- `GET /api/records`
- `POST /api/enquiry`

