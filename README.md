# Calendar Availability Finder

Find time slots that are free across multiple Google Calendar accounts in a single view.

## Why it exists

Scheduling across two or more Google accounts (e.g. a personal calendar and a company calendar) is a constant friction. Google Calendar's UI only shows your own free time clearly; overlapping availability across accounts is hidden behind manual checking. This tool reads both calendars via the Google Calendar API and outputs the intersection of free slots.

## What it does

- Reads multiple Google Calendar accounts via OAuth
- Computes the intersection of busy/free across all configured calendars
- Outputs candidate free slots within a given date range and working-hour window
- Useful for sharing availability with someone who needs a single combined view

## Stack

- Python
- Google Calendar API (OAuth 2.0)

## Setup

```bash
pip install -r requirements.txt
```

Follow the Google Cloud Console steps in `docs/setup.md` to create OAuth credentials, then place `credentials.json` in the project root and run:

```bash
python find_availability.py --start 2026-05-21 --end 2026-05-31 --hours 09:00-18:00
```

---

Built by [Keigo Yoshinaga](https://github.com/yoshinagak-sudo).
