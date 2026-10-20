import os
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "dummy-anon-key")

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True

    with flask_app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def _isolate_activity_log(monkeypatch):
    """The activity log talks to Supabase through its own client (activity.supabase),
    separate from the `tasks.supabase` that the route tests mock. Replace it with a
    harmless fake so no test ever makes a real network call or writes a log row."""
    from unittest.mock import MagicMock
    import activity
    monkeypatch.setattr(activity, "supabase", MagicMock())

    import routes.tasks as tasks
    for name in ("notify_project", "create_notifications"):
        if hasattr(tasks, name):
            monkeypatch.setattr(tasks, name, lambda *a, **k: None)
    for name in ("display_name", "project_name"):
        if hasattr(tasks, name):
            monkeypatch.setattr(tasks, name, lambda *a, **k: "Someone")

    if hasattr(activity, "clear_caches"):
        activity.clear_caches()
    yield
    if hasattr(activity, "clear_caches"):
        activity.clear_caches()
