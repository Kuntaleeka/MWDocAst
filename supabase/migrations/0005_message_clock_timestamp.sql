-- A question and its pending answer are inserted in one transaction, where now() is constant, so
-- both got the same created_at and history ordering was ambiguous. clock_timestamp() advances.
alter table public.messages alter column created_at set default clock_timestamp();
