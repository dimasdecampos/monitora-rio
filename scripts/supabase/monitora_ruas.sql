-- Monitor dos Rios: ruas que alagam e com que nível, editáveis na página /admin. Rodar uma vez no Supabase "estoura".
-- Pode rodar de novo sem problema.
--
-- O mapa "O que alaga" do painel lê monitora_ruas_listar (aberta, só leitura); sem resposta, usa o impactos.json da bacia.
-- Gravar exige a senha da /admin (só o hash fica aqui). Ela é separada do token do robô de avisos.
-- Para definir ou trocar a senha, no SQL Editor:
--   delete from public.monitora_admin;
--   insert into public.monitora_admin (senha_hash) values (encode(sha256(convert_to('SUA SENHA AQUI', 'UTF8')), 'hex'));

create table if not exists public.monitora_admin (senha_hash text primary key);
alter table public.monitora_admin enable row level security;   -- sem políticas: só as funções abaixo leem

create table if not exists public.monitora_ruas (
  bacia text not null check (bacia ~ '^[a-z0-9-]{1,40}$'),
  nome text not null check (length(nome) between 2 and 120),
  cm real not null check (cm between 0 and 2000),          -- nível na régua principal em que começa a alagar
  aproximado boolean not null default false,
  obs text check (length(obs) <= 500),
  lat double precision, lon double precision,              -- ponto (lugar sem traçado, ou onde abrir o balão)
  linhas jsonb,                                            -- [[[lat, lon], ...], ...] (ruas, do OpenStreetMap)
  area jsonb,                                              -- [[lat, lon], ...] (praça)
  ativo boolean not null default true,
  atualizado_em timestamptz not null default now(),
  primary key (bacia, nome),
  check (pg_column_size(linhas) <= 60000 and pg_column_size(area) <= 20000)
);
alter table public.monitora_ruas enable row level security;     -- sem políticas: acesso só pelas funções

create or replace function public.monitora_admin_ok(p_senha text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.monitora_admin
                 where senha_hash = encode(sha256(convert_to(coalesce(p_senha, ''), 'UTF8')), 'hex'));
$$;

create or replace function public.monitora_ruas_listar(p_bacia text)
returns table (nome text, cm real, aproximado boolean, obs text, lat double precision, lon double precision,
               linhas jsonb, area jsonb, ativo boolean, atualizado_em timestamptz)
language sql stable security definer set search_path = '' as $$
  select r.nome, r.cm, r.aproximado, r.obs, r.lat, r.lon, r.linhas, r.area, r.ativo, r.atualizado_em
  from public.monitora_ruas r where r.bacia = p_bacia order by r.cm, r.nome;
$$;

create or replace function public.monitora_ruas_salvar(p_senha text, p_bacia text, p_nome text, p_cm real,
  p_aproximado boolean default false, p_obs text default null, p_lat double precision default null, p_lon double precision default null,
  p_linhas jsonb default null, p_area jsonb default null, p_ativo boolean default true, p_nome_antigo text default null)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.monitora_admin_ok(p_senha) then raise exception 'senha errada'; end if;
  if p_lat is null and p_linhas is null and p_area is null then raise exception 'falta o lugar (ponto, rua ou área)'; end if;
  if (select count(*) from public.monitora_ruas where bacia = p_bacia) >= 3000 then raise exception 'trechos demais'; end if;
  if p_nome_antigo is not null and p_nome_antigo <> p_nome then
    delete from public.monitora_ruas where bacia = p_bacia and nome = p_nome_antigo;
  end if;
  insert into public.monitora_ruas (bacia, nome, cm, aproximado, obs, lat, lon, linhas, area, ativo, atualizado_em)
  values (p_bacia, trim(p_nome), p_cm, coalesce(p_aproximado, false), nullif(trim(p_obs), ''), p_lat, p_lon, p_linhas, p_area, coalesce(p_ativo, true), now())
  on conflict (bacia, nome) do update set cm = excluded.cm, aproximado = excluded.aproximado, obs = excluded.obs,
    lat = excluded.lat, lon = excluded.lon, linhas = excluded.linhas, area = excluded.area, ativo = excluded.ativo, atualizado_em = now();
end $$;

create or replace function public.monitora_ruas_apagar(p_senha text, p_bacia text, p_nome text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.monitora_admin_ok(p_senha) then raise exception 'senha errada'; end if;
  delete from public.monitora_ruas where bacia = p_bacia and nome = p_nome;
end $$;

-- pincel da /admin: grava e apaga vários trechos de uma vez.
-- p_salvar: [{"nome", "cm", "aproximado"?, "obs"?, "lat"?, "lon"?, "linhas"?, "area"?}, ...]; p_apagar: nomes
create or replace function public.monitora_ruas_lote(p_senha text, p_bacia text, p_salvar jsonb, p_apagar text[])
returns integer language plpgsql security definer set search_path = '' as $$
declare n integer;
begin
  if not public.monitora_admin_ok(p_senha) then raise exception 'senha errada'; end if;
  if jsonb_typeof(p_salvar) <> 'array' or jsonb_array_length(p_salvar) > 1000 or coalesce(array_length(p_apagar, 1), 0) > 1000 then
    raise exception 'lote inválido';
  end if;
  delete from public.monitora_ruas where bacia = p_bacia and nome = any(coalesce(p_apagar, '{}'));
  insert into public.monitora_ruas (bacia, nome, cm, aproximado, obs, lat, lon, linhas, area, ativo, atualizado_em)
  select p_bacia, trim(x->>'nome'), (x->>'cm')::real, coalesce((x->>'aproximado')::boolean, false), nullif(trim(x->>'obs'), ''),
         (x->>'lat')::double precision, (x->>'lon')::double precision, x->'linhas', x->'area', true, now()
  from jsonb_array_elements(p_salvar) x
  on conflict (bacia, nome) do update set cm = excluded.cm, aproximado = excluded.aproximado, obs = excluded.obs,
    lat = excluded.lat, lon = excluded.lon, linhas = excluded.linhas, area = excluded.area, ativo = true, atualizado_em = now();
  select count(*) into n from public.monitora_ruas where bacia = p_bacia;
  if n > 3000 then raise exception 'trechos demais'; end if;
  return n;
end $$;

revoke all on public.monitora_admin, public.monitora_ruas from anon, authenticated;
revoke execute on function public.monitora_admin_ok(text), public.monitora_ruas_listar(text),
  public.monitora_ruas_salvar(text, text, text, real, boolean, text, double precision, double precision, jsonb, jsonb, boolean, text),
  public.monitora_ruas_apagar(text, text, text), public.monitora_ruas_lote(text, text, jsonb, text[]) from public;
grant execute on function public.monitora_admin_ok(text), public.monitora_ruas_listar(text),
  public.monitora_ruas_salvar(text, text, text, real, boolean, text, double precision, double precision, jsonb, jsonb, boolean, text),
  public.monitora_ruas_apagar(text, text, text), public.monitora_ruas_lote(text, text, jsonb, text[]) to anon, authenticated;
notify pgrst, 'reload schema';
