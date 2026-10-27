"""Avisos de cheia por app ntfy, Telegram e WhatsApp, para todas as bacias (roda no GitHub Actions a cada ~10 min).

Avisa, em cada bacia, quando:
  - a régua principal passa para uma cota mais alta (e quando baixa de cota ou volta ao normal);
  - a água sobe rápido numa régua rio acima (≥ 20 cm em 3 h), com o tempo de chegada à cidade;
  - o afluente de "represamento" está cheio junto com o rio alto (se a bacia tiver);
  - a previsão dá 30% ou mais de chance de chegar à próxima cota em 48 h (se a bacia tiver modelo);
  - a régua principal para de transmitir (repete a cada 24 h, ou 6 h se o rio estava em cota) e quando volta.
Cada tipo de aviso se repete no máximo a cada 6–12 h.

Variáveis de ambiente:
  NTFY_TOPIC                      prefixo dos tópicos do app ntfy: cada bacia avisa em <NTFY_TOPIC>-<bacia>
  TELEGRAM_TOKEN                  bot do Telegram; o canal de cada bacia fica em config.json → avisos.telegram_chat
  CALLMEBOT_PHONE, CALLMEBOT_KEY  WhatsApp pessoal via CallMeBot (número com DDI, ex. +5512999999999)
  HEALTHCHECK_URL                 endereço de ping do healthchecks.io (vigia: avisa por e-mail se o robô parar)
  TESTE=1                         envia já uma mensagem de teste com o nível atual de cada bacia
  ESTADO                          pasta onde guarda o que já foi avisado (padrão .alertas/)
Sem nenhum canal configurado, só mostra as mensagens (modo de teste).

Uso: python scripts/alertas.py [--bacia paraitinga]
"""
import argparse, html, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

SITE = "https://dimasdecampos.github.io/monitora-rio/"
SIBH = "https://cth.daee.sp.gov.br/sibh/api/v2/measurements"
BRT = timezone(timedelta(hours=-3))
COTAS = [("extravasamento", "Transbordamento"), ("emergencia", "Emergência"), ("alerta", "Alerta"), ("atencao", "Atenção")]
PASTA_ESTADO = Path(os.environ.get("ESTADO", comum.RAIZ / ".alertas"))


def br(cm):
    """cm -> "2,75" (metros, vírgula decimal)"""
    return f"{cm / 100:.2f}".replace(".", ",")


def obter(url, tentativas=3):
    for n in range(tentativas):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "monitor-rios"}), timeout=90))
        except Exception as e:
            print("erro", e); time.sleep(5 * (n + 1))
    return None


def limpar(serie):
    """descarta salto > 3 m em até 6 h (régua voltando de falha com valor travado)"""
    limpo = []
    for t, v in sorted(serie):
        if limpo and abs(v - limpo[-1][1]) > 300 and (t - limpo[-1][0]) <= timedelta(hours=6): continue
        limpo.append((t, v))
    return limpo


def leituras_sibh(ests, horas=14):
    out = {e["codigo"]: [] for e in ests}
    if not ests: return out
    fim = datetime.now(timezone.utc) + timedelta(hours=1); ini = fim - timedelta(hours=horas + 1)
    por_id = {e["id_nivel"]: e["codigo"] for e in ests}
    ids = list(por_id)
    for k in range(0, len(ids), 10):   # a API aceita no máximo 10 estações por chamada
        q = "&".join(f"station_prefix_ids[]={i}" for i in ids[k:k + 10])
        d = obter(f"{SIBH}?{q}&start_date={ini:%Y-%m-%dT%H:%M}&end_date={fim:%Y-%m-%dT%H:%M}")
        for m in (d or {}).get("measurements", []):
            c = por_id.get(str(m["station_prefix_id"]))
            if m["value"] is None or c is None: continue
            t = datetime.strptime(m["date"], "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
            out[c].append((t, float(m["value"])))
    return {c: limpar(s) for c, s in out.items()}


def leituras_ana(codigo, horas=14):
    hoje = datetime.now(BRT).date()
    try:
        ls = comum.buscar_ana(codigo, hoje - timedelta(days=math.ceil(horas / 24)), hoje + timedelta(days=1))
    except Exception as e:
        print("erro ANA", e); return []
    serie = [(datetime.fromisoformat(l["t"]).replace(tzinfo=BRT).astimezone(timezone.utc), l["nivel"]) for l in ls if l["nivel"] is not None and l["nivel"] >= 0]
    corte = datetime.now(timezone.utc) - timedelta(hours=horas + 1)
    return limpar([x for x in serie if x[0] >= corte])


def variacao(serie, horas):
    if not serie: return None
    t1, v1 = serie[-1]
    antes = [v for t, v in serie if abs((t1 - t).total_seconds() - horas * 3600) <= 1800]
    return v1 - antes[0] if antes else None


def cota_de(cm, cotas):
    return next(((k, n, cotas[k]) for k, n in COTAS if k in cotas and cm >= cotas[k]), None)


def probabilidade(modelo, ref, rio_acima):
    """Chance (0–1) de a régua principal chegar a cada cota em 48 h — mesmo modelo do painel."""
    pm = modelo["passarela"]; pts = modelo["pontos"]
    base = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": ",".join(str(p["lat"]) for p in pts), "longitude": ",".join(str(p["lon"]) for p in pts),
        "hourly": "precipitation", "past_days": 31, "forecast_days": 3, "timezone": "America/Sao_Paulo"})
    d = obter(base)
    if not d: return None
    d = d if isinstance(d, list) else [d]
    tempo = d[0]["hourly"]["time"]; media = [sum((p["hourly"]["precipitation"][i] or 0) for p in d) / len(d) for i in range(len(tempo))]
    agora = datetime.now(BRT).strftime("%Y-%m-%dT%H:00")
    i = max(j for j, t in enumerate(tempo) if t <= agora)
    S = lambda a, b: sum(media[max(0, a):max(0, b)])
    p24, p72, api, f48 = S(i - 24, i + 1), S(i - 72, i + 1), S(i - 720, i - 72), S(i + 1, i + 49) * modelo["fator_previsao"]
    dc6, dc12 = variacao(rio_acima, 6), variacao(rio_acima, 12)
    versao = "B" if dc6 is not None and dc12 is not None and rio_acima and (datetime.now(timezone.utc) - rio_acima[-1][0]) < timedelta(hours=2) else "A"
    def bruta(G, h0=ref):
        f, a, b, s, g = math.log1p(f48), math.log1p(p24), math.log1p(p72), api / 100, G / 100
        v = [1, g, f, a, b, s, h0 / 100, f * s, f * g, a * g, g * g]
        if versao == "B":
            dc = max(dc6, 0) / 100; v += [dc, max(dc12, 0) / 100, dc / (g + .3)]
        w = pm["pesos_B"] if versao == "B" else pm["pesos_A"]
        z = sum(x * y for x, y in zip(w, v)); return 1 / (1 + math.exp(-max(-30, min(30, z))))
    def subir(G, h0=ref):
        # igual ao painel: o termo g² faz a curva voltar a subir em subidas muito grandes;
        # a chance de subir G cm nunca pode ser maior que a de subir menos
        if G <= 0: return 1.0
        return min([bruta(G, h0)] + [bruta(cm, h0) for cm in range(10, int(G), 10)])
    def chance(G):
        # chance de chegar a ref + G: não pode ser maior que a de quem já está mais alto chegar lá
        alvo = ref + G
        return min([subir(G)] + [subir(alvo - h, h) for h in range(int(ref) + 10, int(alvo), 10)])
    return chance, f48


def verificar(bacia, mandar):
    """Confere uma bacia e manda os avisos novos com mandar(cfg, texto) -> True se chegou.

    Um aviso só conta como dado (e não se repete) depois de chegar por pelo menos um canal;
    se todos falharem, ele é tentado de novo na próxima rodada. Devolve quantos falharam."""
    cfg = comum.config(bacia); EST = comum.estacoes(cfg); P = cfg["principal"]
    nome = lambda c: EST[c].get("curto") or EST[c]["nome"]
    arq = PASTA_ESTADO / f"{bacia}.json"
    antigo = PASTA_ESTADO / "estado.json"   # formato antigo, de quando só havia o Paraitinga
    if not arq.exists() and bacia == "paraitinga" and antigo.exists(): arq.write_text(antigo.read_text())
    estado = json.loads(arq.read_text()) if arq.exists() else {"cota": None, "avisos": {}}
    agora = time.time()
    falhas = 0
    def pode(chave, horas):
        return agora - estado["avisos"].get(chave, 0) >= horas * 3600
    def avisar(texto, chave=None):
        nonlocal falhas
        if mandar(cfg, texto):
            if chave: estado["avisos"][chave] = agora
            return True
        falhas += 1; print(f"{bacia}: aviso não chegou por nenhum canal; tenta de novo na próxima rodada")
        return False
    def gravar():
        PASTA_ESTADO.mkdir(exist_ok=True); arq.write_text(json.dumps(estado))

    acima = [c for c, e in EST.items() if e.get("rio_acima", {}).get("horas_ate_cidade") and not e["rio_acima"].get("afluente")]
    extras = [cfg["represamento"]["afluente"]] if cfg.get("represamento") else []
    if cfg.get("previsao", {}) and cfg["previsao"].get("rio_acima"): extras.append(cfg["previsao"]["rio_acima"])
    codigos = list(dict.fromkeys([P, *acima, *extras]))
    s = leituras_sibh([EST[c] for c in codigos if EST[c]["fonte"] == "spaguas"])
    for c in codigos:
        if EST[c]["fonte"] == "ana": s[c] = leituras_ana(c)

    cid = s[P]; cot_p = {k: v for k, v in EST[P].get("cotas_cm", {}).items() if k in dict(COTAS)}
    # 0) régua principal sem dados: avisa (sem isso, quem segue o canal acharia que está tudo calmo)
    rio = cfg["rio"]
    if cid and cid[-1][0].timestamp() >= estado.get("ultima_leitura", 0):
        estado["ultima_leitura"] = cid[-1][0].timestamp(); estado["ultimo_nivel"] = cid[-1][1]
    ult = estado.get("ultima_leitura")
    if ult is None or agora - ult > (EST[P].get("atraso_max_horas", 1) + 1) * 3600:
        # conta as rodadas seguidas sem dados: uma falha passageira da API não dispara aviso
        estado["sem_dados_rodadas"] = estado.get("sem_dados_rodadas", 0) + 1
        print(f"{bacia}: {nome(P)} sem leitura recente ({estado['sem_dados_rodadas']}ª rodada); nada a avisar sobre o nível.")
        cota = estado.get("cota")
        if estado["sem_dados_rodadas"] >= 2 and pode("sem-dados", 6 if cota else 24):
            if ult:
                desde = f"Última leitura: {br(estado['ultimo_nivel'])} m em {datetime.fromtimestamp(ult, BRT):%d/%m às %H:%M}."
            else:
                desde = "Nenhuma leitura nas últimas 14 h."
            if cota:
                titulo = f"⚠️ *{rio}: régua sem dados durante {dict(COTAS)[cota].lower()}*"
            else:
                titulo = f"📡 *{rio}: régua sem dados*"
            if avisar(f"{titulo}\n{nome(P)} parou de transmitir. {desde}\n"
                      f"Enquanto isso, os avisos de nível ficam parados. Em caso de risco, Defesa Civil: 199.", "sem-dados"):
                estado["sem_dados_avisado"] = True
        gravar(); return falhas
    if not cid:   # a API falhou agora, mas a última leitura ainda é recente: espera a próxima rodada
        print(f"{bacia}: {nome(P)} sem resposta agora; última leitura ainda recente."); gravar(); return falhas
    estado["sem_dados_rodadas"] = 0
    estado["avisos"].pop("sem-dados", None)   # uma nova queda avisa logo, sem esperar 24 h
    nivel = cid[-1][1]; hora = cid[-1][0].astimezone(BRT).strftime("%H:%M")
    if estado.get("sem_dados_avisado") and avisar(f"✅ *{rio}: régua voltou a transmitir*\n{nome(P)} em {br(nivel)} m às {hora}."):
        estado.pop("sem_dados_avisado")
    d3 = variacao(cid, 3)
    tend = "" if d3 is None else f", {'subindo' if d3 >= 5 else 'baixando' if d3 <= -5 else 'estável'} ({d3:+.0f} cm em 3 h)"

    # 1) cota da cidade (sobe na hora; desce só 5 cm abaixo, para não ficar avisando)
    atual = cota_de(nivel, cot_p) if cot_p else None
    ordem = [k for k, _ in COTAS]
    anterior = estado.get("cota")
    if anterior and anterior in cot_p and (not atual or ordem.index(atual[0]) > ordem.index(anterior)) and nivel > cot_p[anterior] - 5:
        atual = (anterior, dict(COTAS)[anterior], cot_p[anterior])
    msg = None
    if atual and atual[0] != anterior and (not anterior or ordem.index(atual[0]) < ordem.index(anterior)):
        msg = (f"🔴 *{rio}: {atual[1]}*\n{nome(P)} em *{br(nivel)} m* às {hora}{tend}.\nCota de {atual[1].lower()}: {br(atual[2])} m.")
    elif anterior and not atual:
        msg = f"🟢 *{rio} abaixo da atenção*\n{nome(P)} em {br(nivel)} m às {hora}{tend}."
    elif atual and anterior and atual[0] != anterior:
        msg = f"🟠 *{rio} baixando: {atual[1]}*\n{nome(P)} em {br(nivel)} m às {hora}{tend}."
    if msg is None or avisar(msg):   # se o aviso não chegou, a mudança de cota é avisada de novo na próxima rodada
        estado["cota"] = atual[0] if atual else None

    # 2) água subindo rio acima
    for c in acima:
        d = variacao(s.get(c, []), 3)
        if d is not None and d >= 20 and pode("sobe-" + c, 6):
            avisar(f"🌊 *Água subindo em {EST[c]['nome']}*\n+{d:.0f} cm em 3 h ({br(s[c][-1][1])} m). Chega a {cfg['cidade']} em cerca de {EST[c]['rio_acima']['horas_ate_cidade']} h.", "sobe-" + c)

    # 3) represamento por um afluente que deságua logo abaixo da cidade
    rep = cfg.get("represamento")
    if rep:
        ch = s.get(rep["afluente"], []); at = EST[rep["afluente"]]["cotas_cm"].get("atencao")
        if ch and at and ch[-1][1] >= at and "alerta" in cot_p and nivel >= cot_p["alerta"] and pode("represa", 12):
            avisar(f"⚠️ *Risco de represamento*\n{rep['nome']} em {br(ch[-1][1])} m com o {rio.replace('Rio ', '')} em {br(nivel)} m: a água pode represar perto da cidade.", "represa")

    # 4) previsão (só bacias com modelo)
    if cfg.get("previsao") and cot_p:
        modelo = json.loads((comum.pasta(bacia) / cfg["previsao"]["modelo"]).read_text(encoding="utf-8"))
        r = probabilidade(modelo, nivel, s.get(cfg["previsao"].get("rio_acima"), []))
        if r:
            chance, f48 = r
            prox = next(((k, n, cot_p[k]) for k, n in reversed(COTAS) if k in cot_p and nivel < cot_p[k]), None)
            if prox:
                p = chance(prox[2] - nivel)
                print(f"{bacia}: previsão {p*100:.0f}% de chegar a {prox[1]} ({br(prox[2])} m); chuva prevista 48 h {f48:.0f} mm")
                if p >= .3 and pode("prev-" + prox[0], 12):
                    avisar(f"🌧️ *Previsão: {p*100:.0f}% de chance de {prox[1].lower()}*\nNas próximas 48 h, {nome(P)} pode chegar a {br(prox[2])} m (agora {br(nivel)} m). Chuva prevista na bacia: {f48:.0f} mm.", "prev-" + prox[0])

    if os.environ.get("TESTE") == "1":
        sit = atual[1] if atual else "Normal" if cot_p else "sem cotas"
        avisar(f"🧪 *Teste: {rio}*\n{nome(P)} em *{br(nivel)} m* às {hora}{tend}. Situação: {sit}.")

    print(f"{bacia}: {nome(P)} {br(nivel)} m às {hora}; cota: {estado['cota']}; {falhas} aviso(s) sem entregar")
    gravar()
    return falhas


def telegram_html(m, link):
    """*negrito* -> <b>negrito</b>, com o resto escapado (nomes com _ ou * não quebram a mensagem)."""
    t = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", html.escape(m, quote=False))
    return t + f'\n\n<a href="{html.escape(link)}">Abrir o painel</a>'


def enviar(cfg, m):
    """Manda o aviso pelos canais configurados (ntfy, Telegram, WhatsApp). True se chegou por pelo menos um."""
    ok = False
    link = SITE + cfg["id"] + "/"
    token, chat = os.environ.get("TELEGRAM_TOKEN"), (cfg.get("avisos") or {}).get("telegram_chat")
    fone, chave = os.environ.get("CALLMEBOT_PHONE"), os.environ.get("CALLMEBOT_KEY")
    prefixo = os.environ.get("NTFY_TOPIC")
    if prefixo:
        # notificação no app ntfy: primeira linha vira título; vermelho/onda/represa tocam como urgentes
        titulo, _, corpo = m.replace("*", "").partition("\n")
        prio = "5" if m[:1] in "🔴🌊⚠" else "3" if m[:1] in "🟢🧪✅" else "4"
        req = urllib.request.Request(f"https://ntfy.sh/{prefixo}-{cfg['id']}", data=corpo.encode("utf-8"), method="POST",
                                     headers={"Title": titulo.encode("utf-8").decode("latin-1"), "Priority": prio, "Click": link})
        try:
            urllib.request.urlopen(req, timeout=30); ok = True
        except Exception as e:
            print("falha no ntfy:", e)
    if token and chat:
        dados = urllib.parse.urlencode({"chat_id": chat, "text": telegram_html(m, link), "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=dados, timeout=30); ok = True
        except urllib.error.HTTPError as e:
            print("falha no Telegram:", e, e.read()[:300])
        except Exception as e:
            print("falha no Telegram:", e)
    if fone and chave:
        # WhatsApp usa *negrito* igual ao Telegram, mas não aceita [texto](link)
        q = urllib.parse.urlencode({"phone": fone, "text": m + f"\n\nPainel: {link}", "apikey": chave})
        for n in range(3):
            try:
                r = urllib.request.urlopen(f"https://api.callmebot.com/whatsapp.php?{q}", timeout=60).read().decode("utf-8", "replace")
                if "queued" in r.lower() or "sent" in r.lower(): ok = True; break
                print("CallMeBot respondeu:", r[:300])
            except Exception as e:
                print("falha no WhatsApp:", e)
            time.sleep(10 * (n + 1))
        time.sleep(5)   # o CallMeBot recusa mensagens muito seguidas
    if not prefixo and not (token and chat) and not (fone and chave):
        print("--- (teste, sem canal configurado) ---\n" + m)
        return True
    return ok


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bacia", help="só esta bacia; padrão: todas")
    a = p.parse_args()
    erros = 0
    for bacia in [a.bacia] if a.bacia else comum.bacias():
        try:
            erros += verificar(bacia, enviar)
        except Exception as e:   # uma bacia com problema não impede as outras
            print(f"{bacia}: erro {e!r}"); erros += 1
    vigia(erros)
    if erros:   # rodada vermelha no GitHub (e e-mail para o dono do repositório)
        sys.exit(f"{erros} problema(s) nesta rodada")


def vigia(erros):
    """Avisa o healthchecks.io que o robô rodou. Se ele parar de rodar (ou der erro), o site manda e-mail."""
    url = os.environ.get("HEALTHCHECK_URL")
    if not url: return
    try:
        urllib.request.urlopen(url.rstrip("/") + ("/fail" if erros else ""), timeout=15)
    except Exception as e:
        print("falha ao avisar o vigia:", e)


if __name__ == "__main__":
    main()
