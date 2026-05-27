-- 002_oauth_tokens.sql
-- Stores OAuth credentials per provider (Whoop). One row per provider; the
-- refresh token lets the app mint new access tokens without re-authorizing.
-- Run in the Supabase SQL editor after 001_initial_schema.sql.

create table if not exists oauth_tokens (
    provider      text primary key,
    access_token  text,
    refresh_token text,
    expires_at    timestamptz,
    scope         text,
    updated_at    timestamptz not null default now()
);
