import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()  # no-op in production where env vars are set directly (e.g. on Render)

SUPABASE_URL = os.environ["SUPABASE_URL"]

# Service role key — server-side only, NEVER send this to the frontend.
# It bypasses RLS, which is fine because Flask does its own permission
# checks (see auth_utils.py) before touching the database.
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Anon key — safe to also expose to the frontend. Used here only for
# verifying user JWTs; the frontend uses it directly for auth calls.
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
supabase_auth: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def maybe_one(query):
    """Run a .maybe_single() query safely.

    In supabase-py 2.x, .maybe_single().execute() returns None (not a
    response object) when no row matches, so reading `.data` on it
    crashes. This returns the row as a dict, or None if there isn't one.
    """
    result = query.maybe_single().execute()
    return result.data if result is not None else None