-- 003_rls_policies.sql
-- Fixes "new row violates row-level security policy" (Postgres error 42501).
--
-- Tables in Supabase's exposed `public` schema have row-level security in
-- effect, but the initial migrations never created any policies, so every
-- write through the project API key (anon/authenticated) was denied.
--
-- This is a single-user app: access is already gated by APP_PASSWORD at the
-- Streamlit layer, and the Supabase key lives only in server-side secrets,
-- never in a browser. So a permissive "allow everything" policy per table is
-- the intended posture. (Alternatively, skip this migration and use the
-- service_role key as SUPABASE_KEY, which bypasses RLS entirely.)
--
-- Idempotent: safe to run more than once. Run in the Supabase SQL editor.

do $$
declare
    t text;
    tables text[] := array[
        'oauth_tokens', 'goals', 'garmin_raw', 'whoop_raw', 'daily_metrics',
        'workouts', 'training_plan', 'plan_revisions', 'progress_tests',
        'qa_log', 'debug_log'
    ];
begin
    foreach t in array tables loop
        execute format('alter table %I enable row level security;', t);
        execute format('drop policy if exists app_all on %I;', t);
        -- Full read/write for the API roles the app connects as.
        execute format(
            'create policy app_all on %I for all to anon, authenticated '
            'using (true) with check (true);', t
        );
    end loop;
end $$;
