-- Transactional integration checks: leave no accounts or invoice records behind.
begin;
insert into auth.users (id, aud, role, email, email_confirmed_at, created_at, updated_at)
values ('12345678-1111-4444-8888-123456789001','authenticated','authenticated','invoice-test-one@example.invalid',now(),now(),now()),
       ('12345678-1111-4444-8888-123456789002','authenticated','authenticated','invoice-test-two@example.invalid',now(),now(),now());
set local role anon;
do $$ begin
    begin
        perform public.invoice_trial_usage();
        raise exception 'Anonymous access was allowed';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','12345678-1111-4444-8888-123456789001',true);
do $$ begin
    assert public.invoice_trial_usage() = 0, 'New account not empty';
    assert public.claim_invoice_trial(repeat('a',64)) = 1, 'First invoice denied';
    assert public.claim_invoice_trial(repeat('b',64)) = 2, 'Second invoice denied';
    begin
        perform public.claim_invoice_trial(repeat('c',64));
        raise exception 'Third invoice was allowed' using errcode = '23514';
    exception when raise_exception then
        if sqlerrm <> 'INVOICE_TRIAL_EXHAUSTED' then raise; end if;
    end;
    begin
        perform public.claim_invoice_trial(repeat('a',64));
        raise exception 'Old download replay was allowed' using errcode = '23514';
    exception when raise_exception then
        if sqlerrm <> 'INVOICE_TRIAL_EXHAUSTED' then raise; end if;
    end;
    assert public.invoice_trial_usage() = 2, 'Usage changed after rejection';
    begin
        perform * from public.invoice_trial_exports;
        raise exception 'Direct table read allowed' using errcode = '23514';
    exception when insufficient_privilege then null;
    end;
    begin
        delete from public.invoice_trial_exports;
        raise exception 'Direct reset allowed' using errcode = '23514';
    exception when insufficient_privilege then null;
    end;
end $$;
select set_config('request.jwt.claim.sub','12345678-1111-4444-8888-123456789002',true);
do $$ begin
    assert public.invoice_trial_usage() = 0, 'Accounts not isolated';
    assert public.claim_invoice_trial(repeat('a',64)) = 1, 'Other account lacks own allowance';
end $$;
reset role;
rollback;
select 'PASS: two invoices, exhausted replay denied, third denied, account isolation and restricted table access' as result;
