-- Einmalig im Supabase SQL Editor ausführen.
alter table public.items
add column if not exists image_url text;
