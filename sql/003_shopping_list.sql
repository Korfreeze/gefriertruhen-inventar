create table if not exists shopping_list (
  id bigint generated always as identity primary key,
  name text not null,
  quantity numeric not null default 1 check (quantity >= 0),
  unit text not null default 'Stück',
  checked boolean not null default false,
  source_item_id bigint references items(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table shopping_list enable row level security;

drop policy if exists "authenticated can read shopping list" on shopping_list;
drop policy if exists "authenticated can insert shopping list" on shopping_list;
drop policy if exists "authenticated can update shopping list" on shopping_list;
drop policy if exists "authenticated can delete shopping list" on shopping_list;

create policy "authenticated can read shopping list"
on shopping_list for select to authenticated using (true);

create policy "authenticated can insert shopping list"
on shopping_list for insert to authenticated with check (true);

create policy "authenticated can update shopping list"
on shopping_list for update to authenticated using (true) with check (true);

create policy "authenticated can delete shopping list"
on shopping_list for delete to authenticated using (true);

create or replace function update_shopping_list_timestamp()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists shopping_list_updated_at on shopping_list;
create trigger shopping_list_updated_at
before update on shopping_list
for each row execute function update_shopping_list_timestamp();

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'shopping_list'
  ) then
    alter publication supabase_realtime add table shopping_list;
  end if;
end $$;
