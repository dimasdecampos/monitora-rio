-- Monitor dos Rios: inscrições de notificação (Web Push), no projeto Supabase "estoura".
-- Só cria objetos com prefixo monitora_; não toca em nada do estoura.
-- Acesso do público só pelas funções (validam os dados); a lista de inscritos só sai com a senha do robô.

create table if not exists public.monitora_push (
  endpoint text not null,
  p256dh   text not null,
  auth     text not null,
  bacia    text not null,
  criado   timestamptz not null default now(),
  primary key (endpoint, bacia)
);
comment on table public.monitora_push is 'Monitor dos Rios: aparelhos inscritos nos avisos de cheia (Web Push). Sem dados pessoais.';
alter table public.monitora_push enable row level security;
revoke all on public.monitora_push from anon, authenticated;

-- hash (sha256) da senha do robô de avisos; a senha em si fica só no GitHub (MONITORA_PUSH_TOKEN)
create table if not exists public.monitora_segredo (
  id int primary key default 1 check (id = 1),
  token_hash text not null
);
alter table public.monitora_segredo enable row level security;
revoke all on public.monitora_segredo from anon, authenticated;

create or replace function public.monitora_inscrever(p_endpoint text, p_p256dh text, p_auth text, p_bacia text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_endpoint !~ '^https://[A-Za-z0-9.-]+/' or length(p_endpoint) > 1000
     or coalesce(length(p_p256dh), 0) not between 20 and 200 or coalesce(length(p_auth), 0) not between 8 and 100
     or p_bacia !~ '^[a-z0-9-]{1,40}$' then
    raise exception 'inscrição inválida';
  end if;
  if (select count(*) from public.monitora_push) >= 100000 then raise exception 'limite de inscrições'; end if;
  insert into public.monitora_push (endpoint, p256dh, auth, bacia) values (p_endpoint, p_p256dh, p_auth, p_bacia)
  on conflict (endpoint, bacia) do update set p256dh = excluded.p256dh, auth = excluded.auth;
end $$;

create or replace function public.monitora_cancelar(p_endpoint text, p_bacia text default null)
returns void language sql security definer set search_path = '' as $$
  delete from public.monitora_push where endpoint = p_endpoint and (p_bacia is null or bacia = p_bacia);
$$;

create or replace function public.monitora_autorizado(p_token text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.monitora_segredo
                 where token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'UTF8')), 'hex'));
$$;

create or replace function public.monitora_listar(p_token text, p_bacia text)
returns table (endpoint text, p256dh text, auth text) language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.monitora_autorizado(p_token) then raise exception 'não autorizado'; end if;
  return query select m.endpoint, m.p256dh, m.auth from public.monitora_push m where m.bacia = p_bacia;
end $$;

create or replace function public.monitora_remover(p_token text, p_endpoint text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.monitora_autorizado(p_token) then raise exception 'não autorizado'; end if;
  delete from public.monitora_push where endpoint = p_endpoint;
end $$;

revoke execute on function public.monitora_inscrever(text, text, text, text), public.monitora_cancelar(text, text),
  public.monitora_autorizado(text), public.monitora_listar(text, text), public.monitora_remover(text, text) from public;
grant execute on function public.monitora_inscrever(text, text, text, text), public.monitora_cancelar(text, text),
  public.monitora_listar(text, text), public.monitora_remover(text, text) to anon, authenticated;
