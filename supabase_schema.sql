-- Run this in your Supabase SQL editor at supabase.com/dashboard

-- Users table
create table if not exists users (
  id               bigserial primary key,
  telegram_id      bigint unique not null,
  username         text default '',
  full_name        text default '',
  credits          integer not null default 3,
  total_analyses   integer not null default 0,
  plan             text not null default 'free',
  created_at       timestamptz default now()
);

-- Transactions table
create table if not exists transactions (
  id             bigserial primary key,
  telegram_id    bigint not null references users(telegram_id),
  reference      text unique not null,
  amount_kobo    integer not null,
  credits        integer not null,
  status         text not null default 'pending',  -- pending | paid | failed
  created_at     timestamptz default now()
);

-- Indexes for fast lookups
create index if not exists idx_users_telegram_id on users(telegram_id);
create index if not exists idx_transactions_reference on transactions(reference);
create index if not exists idx_transactions_telegram_id on transactions(telegram_id);

-- Disable row-level security (bot uses service key — safe server-side only)
alter table users disable row level security;
alter table transactions disable row level security;

-- ── NEW TABLES: run these additions after the original schema ──

-- Referrals table
create table if not exists referrals (
  id              bigserial primary key,
  referrer_id     bigint not null references users(telegram_id),
  referee_id      bigint not null references users(telegram_id),
  credits_awarded integer not null default 0,
  created_at      timestamptz default now(),
  unique(referee_id)
);
create index if not exists idx_referrals_referrer on referrals(referrer_id);

-- Signal posts log (tracks what was auto-posted and when)
create table if not exists signal_posts (
  id           bigserial primary key,
  channel_id   text not null,
  tickers      text[] not null,
  content      text not null,
  posted_at    timestamptz default now()
);

-- Add referral_code column to users
alter table users add column if not exists referral_code text unique;
alter table users add column if not exists referred_by   bigint references users(telegram_id);
alter table users add column if not exists referral_count integer not null default 0;

-- Generate referral codes for existing users (base-36 of telegram_id)
-- You can run this once manually or let the app generate on first /start
