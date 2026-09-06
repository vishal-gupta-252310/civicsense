# CivicSense — AI-Powered Civic Issue Reporting and Resolution System

An MCA project. Citizens report civic issues with a photo, geo-location and a short
description; an AI layer classifies the issue type, assigns a priority and flags
duplicates; and administrators track resolution through an analytics dashboard.

## Architecture

Two services:

- **Django web application** (`civicsense/` + `issues/`) — authentication, roles,
  reporting, status tracking, Leaflet map, upvotes and Chart.js analytics.
- **FastAPI AI micro-service** (`ai_service/`) — exposes `POST /classify` and returns
  `{category, priority, summary}`. Uses LiteLLM when an LLM provider is configured,
  otherwise falls back to a zero-config rule-based classifier so the system runs
  fully offline.

The AI provider is chosen purely by configuration (`LLM_MODEL` / `LLM_API_KEY`),
never by code changes.

## Requirements

- Python 3.11+
- MySQL 8.x (running locally by default)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure the environment
cp .env.example .env
#   DB_PASSWORD : your MySQL password
#   LLM_MODEL   : leave blank to use the offline rule-based classifier,
#                 or set e.g. "gpt-4o-mini" and LLM_API_KEY for real AI

# Create the database and run migrations
mysql -u root -p -e "CREATE DATABASE civicsense CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
python manage.py migrate
```

## Running

Terminal 1 — Django (http://localhost:8000):

```bash
python manage.py runserver
```

Terminal 2 — AI service (http://localhost:8001):

```bash
uvicorn ai_service.main:app --port 8001
```

## Quick test

1. Register an account (choose *Administrator* to unlock analytics).
2. **Report Issue** — allow location, attach a photo, describe the problem.
   The AI fills in category and priority automatically.
3. Reporting the same problem nearby flags it as a likely duplicate.
4. **Issue Map** shows colour-coded markers by priority.
5. Administrators can update status (Open → In Progress → Resolved) with a note,
   and view the **Analytics** dashboard.

## Tests

```bash
python manage.py test issues
```

The suite mirrors the project report's test cases (TC01–TC15): registration, login,
reporting (with/without location), AI classification, duplicate detection, AI-service
fallback, status workflow, upvotes and access control.
