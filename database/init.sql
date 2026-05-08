create extension if not exists pgcrypto;

create table if not exists public.keywords (
  id uuid primary key default gen_random_uuid(),
  keyword text not null unique,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.articles (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  normalized_url text not null unique,
  press text,
  source_type text not null default 'naver_news_search',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  current_version integer not null default 1 check (current_version >= 1),
  is_deleted boolean not null default false,
  deleted_at timestamptz,
  last_keyword text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.article_versions (
  id uuid primary key default gen_random_uuid(),
  article_id uuid not null references public.articles(id) on delete cascade,
  version integer not null check (version >= 1),
  keyword text,
  title text,
  content text,
  content_plain text,
  image_urls jsonb not null default '[]'::jsonb,
  image_hashes jsonb not null default '[]'::jsonb,
  title_hash text,
  content_hash text,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (article_id, version)
);

create table if not exists public.article_changes (
  id uuid primary key default gen_random_uuid(),
  article_id uuid not null references public.articles(id) on delete cascade,
  from_version integer,
  to_version integer,
  title_changed boolean not null default false,
  body_changed boolean not null default false,
  image_changed boolean not null default false,
  deleted_changed boolean not null default false,
  change_score numeric(8, 5) not null default 0,
  title_change_ratio numeric(8, 5) not null default 0,
  body_change_ratio numeric(8, 5) not null default 0,
  image_change_ratio numeric(8, 5) not null default 0,
  changed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (article_id, from_version, to_version)
);

create index if not exists idx_keywords_active
  on public.keywords (is_active, keyword);

create index if not exists idx_articles_last_seen
  on public.articles (last_seen_at desc);

create index if not exists idx_articles_deleted
  on public.articles (is_deleted, deleted_at desc);

create index if not exists idx_article_versions_article_version
  on public.article_versions (article_id, version desc);

create index if not exists idx_article_versions_fetched_at
  on public.article_versions (fetched_at desc);

create index if not exists idx_article_changes_changed_at
  on public.article_changes (changed_at desc);

create index if not exists idx_article_changes_article
  on public.article_changes (article_id, to_version desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_keywords_updated_at on public.keywords;
create trigger set_keywords_updated_at
before update on public.keywords
for each row execute function public.set_updated_at();

drop trigger if exists set_articles_updated_at on public.articles;
create trigger set_articles_updated_at
before update on public.articles
for each row execute function public.set_updated_at();

alter table public.keywords enable row level security;
alter table public.articles enable row level security;
alter table public.article_versions enable row level security;
alter table public.article_changes enable row level security;

drop policy if exists "Public read keywords" on public.keywords;
create policy "Public read keywords"
on public.keywords for select
using (true);

drop policy if exists "Public read articles" on public.articles;
create policy "Public read articles"
on public.articles for select
using (true);

drop policy if exists "Public read article versions" on public.article_versions;
create policy "Public read article versions"
on public.article_versions for select
using (true);

drop policy if exists "Public read article changes" on public.article_changes;
create policy "Public read article changes"
on public.article_changes for select
using (true);

insert into public.keywords (keyword)
values
  ('빙그레'),
  ('삼양식품'),
  ('농심')
on conflict (keyword) do nothing;
