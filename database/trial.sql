begin;
-- Run once in the Supabase SQL editor. All quota decisions use the verified JWT.
create table if not exists public.invoice_trial_exports (
    user_id uuid not null references auth.users(id) on delete cascade,
    fingerprint text not null check (fingerprint ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    primary key (user_id, fingerprint)
);
alter table public.invoice_trial_exports enable row level security;
revoke all on public.invoice_trial_exports from anon, authenticated;

create or replace function public.invoice_trial_usage()
returns integer language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null or not exists (select 1 from auth.users where id = auth.uid() and email_confirmed_at is not null) then
        raise exception 'Sign in required' using errcode = '42501';
    end if;
    return (select count(*)::integer from public.invoice_trial_exports where user_id = auth.uid());
end;
$$;

create or replace function public.claim_invoice_trial(p_fingerprint text)
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_user uuid := auth.uid();
    v_used integer;
begin
    if v_user is null or not exists (select 1 from auth.users where id = v_user and email_confirmed_at is not null) then
        raise exception 'Sign in required' using errcode = '42501';
    end if;
    if p_fingerprint is null or p_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'Invalid invoice fingerprint' using errcode = '22023';
    end if;
    -- Serialize concurrent requests for the same account, including multiple tabs.
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_user::text, 0));
    select count(*)::integer into v_used from public.invoice_trial_exports where user_id = v_user;
    -- Check quota before any duplicate handling: exhausted accounts cannot
    -- replay an old fingerprint to authorize another download.
    if v_used >= 2 then
        raise exception 'INVOICE_TRIAL_EXHAUSTED' using errcode = 'P0001';
    end if;
    insert into public.invoice_trial_exports(user_id, fingerprint) values (v_user, p_fingerprint);
    return v_used + 1;
end;
$$;
revoke all on function public.invoice_trial_usage() from public, anon;
revoke all on function public.claim_invoice_trial(text) from public, anon;
grant execute on function public.invoice_trial_usage() to authenticated;
grant execute on function public.claim_invoice_trial(text) to authenticated;

commit;
