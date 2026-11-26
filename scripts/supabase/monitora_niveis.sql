-- Monitor dos Rios: nível mínimo dos avisos por aparelho (Web Push). Rodar uma vez no SQL Editor do Supabase "estoura",
-- depois de monitora_push.sql. Pode rodar de novo sem problema.
-- Cada inscrição guarda a partir de que cota o aparelho quer ser avisado: atencao (tudo), alerta, emergencia ou extravasamento.
-- Quem se inscreveu antes fica com 'atencao' (continua recebendo tudo).

alter table public.monitora_push add column if not exists nivel text not null default 'atencao';
alter table public.monitora_push drop constraint if exists monitora_push_nivel_ok;
alter table public.monitora_push add constraint monitora_push_nivel_ok
  check (nivel in ('atencao', 'alerta', 'emergencia', 'extravasamento'));

-- inscrever: ganha p_nivel (opcional; o painel antigo, sem ele, continua funcionando)
drop function if exists public.monitora_inscrever(text, text, text, text);
create or replace function public.monitora_inscrever(p_endpoint text, p_p256dh text, p_auth text, p_bacia text, p_nivel text default 'atencao')
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_endpoint !~ '^https://[A-Za-z0-9.-]+/' or length(p_endpoint) > 1000
     or coalesce(length(p_p256dh), 0) not between 20 and 200 or coalesce(length(p_auth), 0) not between 8 and 100
     or p_bacia !~ '^[a-z0-9-]{1,40}$'
     or coalesce(p_nivel, 'atencao') not in ('atencao', 'alerta', 'emergencia', 'extravasamento') then
    raise exception 'inscrição inválida';
  end if;
  if (select count(*) from public.monitora_push) >= 100000 then raise exception 'limite de inscrições'; end if;
  insert into public.monitora_push (endpoint, p256dh, auth, bacia, nivel)
  values (p_endpoint, p_p256dh, p_auth, p_bacia, coalesce(p_nivel, 'atencao'))
  on conflict (endpoint, bacia) do update set p256dh = excluded.p256dh, auth = excluded.auth, nivel = excluded.nivel;
end $$;

-- listar: devolve também o nível (o robô filtra por ele)
drop function if exists public.monitora_listar(text, text);
create or replace function public.monitora_listar(p_token text, p_bacia text)
returns table (endpoint text, p256dh text, auth text, nivel text) language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.monitora_autorizado(p_token) then raise exception 'não autorizado'; end if;
  return query select m.endpoint, m.p256dh, m.auth, m.nivel from public.monitora_push m where m.bacia = p_bacia;
end $$;

revoke execute on function public.monitora_inscrever(text, text, text, text, text), public.monitora_listar(text, text) from public;
grant execute on function public.monitora_inscrever(text, text, text, text, text), public.monitora_listar(text, text) to anon, authenticated;
notify pgrst, 'reload schema';
