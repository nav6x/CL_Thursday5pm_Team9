-- Task activity / history log (Sprint 3)
-- Run once in the Supabase SQL Editor.
--
-- One row per change made to a task. `details` holds the structured payload
-- (e.g. {"from": "medium", "to": "high"}); the frontend turns action + details
-- into a readable sentence.
--
-- Design notes:
--   * created_at uses clock_timestamp() (not now()) so events inserted together
--     in one statement still get distinct, ordered timestamps.
--   * task_id has NO foreign key on purpose: when a task is deleted its history
--     (including the "task deleted" event) must survive.
--   * task_name and actor_name are snapshots, so the log still reads correctly
--     after a task is renamed/deleted or a user changes their name.
--   * Rows are only ever inserted by the Flask API (service_role); there is no
--     update or delete route, so the log is append-only.

create table if not exists public.task_activity (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references public.projects(id) on delete cascade,
  task_id     uuid not null,
  task_name   text,
  actor_id    uuid references public.profiles(id) on delete set null,
  actor_name  text,
  action      text not null,
  details     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default clock_timestamp()
);

create index if not exists task_activity_task_idx
  on public.task_activity (task_id, created_at desc);

create index if not exists task_activity_project_idx
  on public.task_activity (project_id, created_at desc);

grant all on public.task_activity to service_role;