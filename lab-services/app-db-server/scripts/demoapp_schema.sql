create table if not exists users (
  id serial primary key,
  username text not null unique,
  role text not null,
  created_at timestamptz not null default now()
);

create table if not exists orders (
  id serial primary key,
  customer text not null,
  status text not null,
  total numeric(10, 2) not null,
  created_at timestamptz not null default now()
);

insert into users (username, role) values
  ('demo', 'analyst'),
  ('ops', 'operator'),
  ('audit', 'viewer')
on conflict (username) do nothing;

insert into orders (customer, status, total) values
  ('north-branch', 'paid', 138.50),
  ('south-branch', 'processing', 94.20),
  ('east-branch', 'shipped', 217.75);
