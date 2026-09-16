# Scrumptious — FIT2101 Team 09

A Kanban-style project management web app, built as the Sprint 1–2 deliverable for FIT2101 (Software Process and Management) at Monash University. Teams create projects, organise work into columns (To Do / In Progress / Done), and manage tasks with priorities, story points, and assignees.

## Tech stack

- **Backend:** Flask (Python), organised as blueprints (`auth`, `projects`, `columns`, `tasks`)
- **Database & Auth:** Supabase (managed Postgres + Auth). The backend uses Supabase's `service_role` key server-side and enforces all authorization itself (role checks in Flask), rather than relying on Postgres Row Level Security — since every request is mediated through this API, not queried directly by the frontend.
- **Frontend:** Vanilla JavaScript and custom CSS (no framework)
- **Testing:** `pytest`, running integration-style tests against the Flask app and a real Supabase test database
- **Deployment:** Render (auto-deploys from `main`)

## Project structure

```
.
├── app.py                 # Flask app entrypoint, blueprint registration
├── config.py               # Supabase client setup (service role + anon)
├── auth_utils.py            # @login_required / @require_role decorators
├── routes/
│   ├── auth.py              # signup, login
│   ├── projects.py          # create/list projects, manage members
│   ├── columns.py           # create/update/delete columns
│   └── tasks.py              # create/update/delete tasks
├── static/js/               # frontend logic (board.js, api.js)
├── board.html, index.html    # frontend pages
└── tests/
    ├── conftest.py           # shared pytest fixtures (client, auth, test project)
    └── test_tasks.py          # tests for task creation + authorization rules
```

## Getting started (local setup)

**1. Clone and set up a virtual environment**
```bash
git clone <repo-url>
cd fit2107-software_project
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Create a `.env` file** in the project root (never commit this — it's in `.gitignore`):
```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
```
Get these values from your Supabase project's **Settings → API** page.

**3. Set up the database schema.** In your Supabase project's SQL Editor, run the schema in [`supabase/schema.sql`](supabase/schema.sql) (creates `profiles`, `projects`, `project_members`, `columns`, `tasks`, `task_assignees`, and grants the required table permissions to `service_role`).

**4. Disable "Confirm email"** under Supabase's **Authentication → Sign In / Providers → Email** — this is a deliberate choice for local development/testing speed, not an oversight; it should be revisited before any real production use.

**5. Run the app**
```bash
python app.py
```
The API is served at `http://127.0.0.1:5000`.

## Running the tests

```bash
pytest -v
```
Tests run against a real Supabase project (not mocks), covering task creation's acceptance criteria (required-field validation, story point range checks, correct project association) and role-based authorization rules.

## API overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup` | Create an account |
| POST | `/api/auth/login` | Log in, returns a JWT |
| GET / POST | `/api/projects` | List / create projects |
| GET / POST | `/api/projects/<id>/members` | List / add project members |
| GET / POST | `/api/projects/<id>/columns` | List / create columns |
| PATCH / DELETE | `/api/projects/<id>/columns/<column_id>` | Update / delete a column |
| GET / POST | `/api/projects/<id>/tasks` | List / create tasks |
| PATCH / DELETE | `/api/projects/<id>/tasks/<task_id>` | Update / delete a task |

All routes except signup/login require an `Authorization: Bearer <token>` header.

## Team

- Ayden Lim
- Nilay Kashid 
- Navadarshanth Shanmugasundaram
- Kaveen Silva
- Yahye Qani

## Project status

Actively in development — Sprint 1/2 of a FIT2101 coursework project.