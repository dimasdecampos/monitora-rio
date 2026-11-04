-- Monitor dos Rios: dispara os robôs do GitHub Actions no horário certo, a partir do Supabase "estoura".
--
-- Por quê: o agendamento do próprio GitHub atrasa muito. Em out–nov/2026 o robô de avisos, marcado para
-- cada 10 min, rodou em média a cada ~5 h (de 3 a 10 h); a coleta diária das 06:20 rodou entre 12h e 16h30.
-- Aqui o pg_cron chama a API do GitHub (workflow_dispatch). O agendamento do GitHub continua como reserva.
--
-- Só cria objetos com prefixo monitora_; não toca em nada do estoura.
-- O token do GitHub fica no Vault com o nome 'monitora_github_token' (veja o README, "Atualização automática").
-- Sem o token, as chamadas não fazem nada.

create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.monitora_disparar(p_workflow text)
returns void language plpgsql security definer set search_path = '' as $$
declare
  v_token text;
begin
  if p_workflow not in ('alertas.yml', 'site.yml') then
    raise exception 'workflow não permitido: %', p_workflow;
  end if;
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'monitora_github_token' limit 1;
  if v_token is null then
    return;   -- token ainda não cadastrado
  end if;
  perform net.http_post(
    url := 'https://api.github.com/repos/dimasdecampos/monitora-rio/actions/workflows/' || p_workflow || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'monitora-rio-supabase'),
    body := jsonb_build_object('ref', 'main'),
    timeout_milliseconds := 10000);
end;
$$;
revoke all on function public.monitora_disparar(text) from public, anon, authenticated;

-- robô de avisos a cada 10 min; coleta e publicação do site todo dia às 06:20 de Brasília (09:20 UTC)
select cron.schedule('monitora-alertas', '*/10 * * * *', $$select public.monitora_disparar('alertas.yml')$$);
select cron.schedule('monitora-site', '20 9 * * *', $$select public.monitora_disparar('site.yml')$$);

-- Conferir se as chamadas estão chegando ao GitHub (204 = ok; 401 = token errado; 404 = token sem acesso ao repositório):
--   select created, status_code, left(content::text, 200) from net._http_response order by created desc limit 10;
