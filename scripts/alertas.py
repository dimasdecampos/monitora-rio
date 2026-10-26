"""Avisos de cheia por Telegram e WhatsApp (roda no GitHub Actions a cada ~10 min).

Avisa quando:
  - a Passarela passa para uma cota oficial mais alta (e quando volta abaixo da atenção);
  - a água sobe rápido numa régua rio acima (≥ 20 cm em 3 h), com o tempo de chegada à cidade;
  - o Ribeirão do Chapéu está cheio junto com o Paraitinga alto (represamento);
  - a previsão dá 30% ou mais de chance de chegar à próxima cota em 48 h.
Cada tipo de aviso se repete no máximo a cada 6–12 h.

Variáveis de ambiente:
  TELEGRAM_TOKEN, TELEGRAM_CHAT   canal do Telegram
  CALLMEBOT_PHONE, CALLMEBOT_KEY  WhatsApp pessoal via CallMeBot (número com DDI, ex. +5512999999999)
                                  sem nenhum dos dois, só mostra as mensagens (modo de teste)
  TESTE=1                         envia já uma mensagem de teste com o nível atual
  ESTADO                          arquivo onde guarda o que já foi avisado (padrão .alertas/estado.json)
"""
import json, math, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SITE = "https://dimasdecampos.github.io/monitora-rio-slp/"
SIBH = "https://cth.daee.sp.gov.br/sibh/api/v2/measurements"
BRT = timezone(timedelta(hours=-3))
config = json.loads((RAIZ / "public" / "config.json").read_text(encoding="utf-8"))
modelo = json.loads((RAIZ / "public" / "modelo_cheias.json").read_text(encoding="utf-8"))
EST = {e["codigo"]: e for r in config["rios"] for e in r["estacoes"]}
COTAS = [("extravasamento", "Transbordamento"), ("emergencia", "Emergência"), ("alerta", "Alerta"), ("atencao", "Atenção")]
ARQ = Path(os.environ.get("ESTADO", RAIZ / ".alertas" / "estado.json"))


def br(cm):
    """cm -> "2,75" (metros, vírgula decimal)"""
    return f"{cm / 100:.2f}".replace(".", ",")


def obter(url, tentativas=3):
    for n in range(tentativas):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "monitor-rio-paraitinga"}), timeout=90))
        except Exception as e:
            print("erro", e); time.sleep(5 * (n + 1))
    return None


def leituras_sibh(codigos, horas=14):
    ids = [EST[c]["id_nivel"] for c in codigos]
    fim = datetime.now(timezone.utc) + timedelta(hours=1); ini = fim - timedelta(hours=horas + 1)
    q = "&".join(f"station_prefix_ids[]={i}" for i in ids)
    d = obter(f"{SIBH}?{q}&start_date={ini:%Y-%m-%dT%H:%M}&end_date={fim:%Y-%m-%dT%H:%M}")
    out = {c: [] for c in codigos}
    por_id = {EST[c]["id_nivel"]: c for c in codigos}
    for m in (d or {}).get("measurements", []):
        if m["value"] is None or m["station_prefix_id"] not in por_id: continue
        t = datetime.strptime(m["date"], "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
        out[por_id[m["station_prefix_id"]]].append((t, float(m["value"])))
    for c in out:
        out[c].sort(); limpo = []
        for t, v in out[c]:   # descarta salto > 3 m em até 6 h (régua voltando de falha com valor travado)
            if limpo and abs(v - limpo[-1][1]) > 300 and (t - limpo[-1][0]) <= timedelta(hours=6): continue
            limpo.append((t, v))
        out[c] = limpo
    return out


def variacao(serie, horas):
    if not serie: return None
    t1, v1 = serie[-1]
    antes = [v for t, v in serie if abs((t1 - t).total_seconds() - horas * 3600) <= 1800]
    return v1 - antes[0] if antes else None


def cota_de(cm, cotas):
    return next(((k, n, cotas[k]) for k, n in COTAS if k in cotas and cm >= cotas[k]), None)


def probabilidade(ref, cunha):
    """Chance (0–1) de a Passarela chegar a cada cota em 48 h — mesmo modelo do painel."""
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
    dc6, dc12 = variacao(cunha, 6), variacao(cunha, 12)
    versao = "B" if dc6 is not None and dc12 is not None and cunha and (datetime.now(timezone.utc) - cunha[-1][0]) < timedelta(hours=2) else "A"
    def chance(G):
        if G <= 0: return 1.0
        f, a, b, s, g = math.log1p(f48), math.log1p(p24), math.log1p(p72), api / 100, G / 100
        v = [1, g, f, a, b, s, ref / 100, f * s, f * g, a * g, g * g]
        if versao == "B":
            dc = max(dc6, 0) / 100; v += [dc, max(dc12, 0) / 100, dc / (g + .3)]
        w = pm["pesos_B"] if versao == "B" else pm["pesos_A"]
        z = sum(x * y for x, y in zip(w, v)); return 1 / (1 + math.exp(-max(-30, min(30, z))))
    return chance, f48


def enviar(m):
    """Manda o aviso para o Telegram e/ou o WhatsApp, conforme os segredos configurados."""
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT")
    fone, chave = os.environ.get("CALLMEBOT_PHONE"), os.environ.get("CALLMEBOT_KEY")
    if token and chat:
        texto = m + f"\n\n[Abrir o painel]({SITE})"
        dados = urllib.parse.urlencode({"chat_id": chat, "text": texto, "parse_mode": "Markdown", "disable_web_page_preview": "true"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=dados, timeout=30)
        except Exception as e:
            print("falha no Telegram:", e)
    if fone and chave:
        # WhatsApp usa *negrito* igual ao Telegram, mas não aceita [texto](link)
        q = urllib.parse.urlencode({"phone": fone, "text": m + f"\n\nPainel: {SITE}", "apikey": chave})
        for n in range(3):
            try:
                r = urllib.request.urlopen(f"https://api.callmebot.com/whatsapp.php?{q}", timeout=60).read().decode("utf-8", "replace")
                if "queued" in r.lower() or "sent" in r.lower(): break
                print("CallMeBot respondeu:", r[:300])
            except Exception as e:
                print("falha no WhatsApp:", e)
            time.sleep(10 * (n + 1))
        time.sleep(5)   # o CallMeBot recusa mensagens muito seguidas
    if not (token and chat) and not (fone and chave):
        print("--- (teste, sem Telegram nem WhatsApp configurado) ---\n" + m)


def main():
    estado = json.loads(ARQ.read_text()) if ARQ.exists() else {"cota": None, "avisos": {}}
    agora = time.time()
    def pode(chave, horas):
        if agora - estado["avisos"].get(chave, 0) < horas * 3600: return False
        estado["avisos"][chave] = agora; return True
    msgs = []
    codigos = ["sp664", "sp35388", "sp662", "sp35402", "sp818", "sp489"]
    s = leituras_sibh(codigos)
    cid = s["sp664"]; cot_p = EST["sp664"]["cotas_cm"]
    if not cid or (datetime.now(timezone.utc) - cid[-1][0]) > timedelta(hours=2):
        print("Passarela sem leitura recente; nada a avisar."); ARQ.parent.mkdir(exist_ok=True); ARQ.write_text(json.dumps(estado)); return
    nivel = cid[-1][1]; hora = cid[-1][0].astimezone(BRT).strftime("%H:%M")
    d3 = variacao(cid, 3)
    tend = "" if d3 is None else f", {'subindo' if d3 >= 5 else 'baixando' if d3 <= -5 else 'estável'} ({d3:+.0f} cm em 3 h)"

    # 1) cota da cidade (sobe na hora; desce só 5 cm abaixo, para não ficar avisando)
    atual = cota_de(nivel, cot_p)
    ordem = [k for k, _ in COTAS]
    anterior = estado.get("cota")
    if anterior and (not atual or ordem.index(atual[0]) > ordem.index(anterior)) and nivel > cot_p[anterior] - 5:
        atual = next((c for c in [(anterior, dict(COTAS)[anterior], cot_p[anterior])]), atual)
    if atual and atual[0] != anterior and (not anterior or ordem.index(atual[0]) < ordem.index(anterior)):
        msgs.append(f"🔴 *Rio Paraitinga: {atual[1]}*\nPassarela em *{br(nivel)} m* às {hora}{tend}.\nCota de {atual[1].lower()}: {br(atual[2])} m.")
    elif anterior and not atual:
        msgs.append(f"🟢 *Rio Paraitinga abaixo da atenção*\nPassarela em {br(nivel)} m às {hora}{tend}.")
    elif atual and anterior and atual[0] != anterior:
        msgs.append(f"🟠 *Rio Paraitinga baixando: {atual[1]}*\nPassarela em {br(nivel)} m às {hora}{tend}.")
    estado["cota"] = atual[0] if atual else None

    # 2) água subindo rio acima
    for c in ["sp818", "sp35402", "sp662", "sp35388"]:
        d = variacao(s[c], 3); e = EST[c]
        if d is not None and d >= 20 and s[c] and pode("sobe-" + c, 6):
            msgs.append(f"🌊 *Água subindo em {e['nome']}*\n+{d:.0f} cm em 3 h ({br(s[c][-1][1])} m). Chega à cidade em cerca de {e['rio_acima']['horas_ate_cidade']} h.")

    # 3) represamento pelo Ribeirão do Chapéu
    ch = s["sp489"]
    if ch and ch[-1][1] >= EST["sp489"]["cotas_cm"]["atencao"] and nivel >= cot_p["alerta"] and pode("represa", 12):
        msgs.append(f"⚠️ *Risco de represamento*\nRibeirão do Chapéu em {br(ch[-1][1])} m com o Paraitinga em {br(nivel)} m: a água pode represar no centro.")

    # 4) previsão
    r = probabilidade(nivel, s["sp818"])
    if r:
        chance, f48 = r
        prox = next(((k, n, cot_p[k]) for k, n in reversed(COTAS) if k in cot_p and nivel < cot_p[k]), None)
        if prox:
            p = chance(prox[2] - nivel)
            print(f"previsão: {p*100:.0f}% de chegar a {prox[1]} ({br(prox[2])} m); chuva prevista 48 h {f48:.0f} mm")
            if p >= .3 and pode("prev-" + prox[0], 12):
                msgs.append(f"🌧️ *Previsão: {p*100:.0f}% de chance de {prox[1].lower()}*\nNas próximas 48 h a Passarela pode chegar a {br(prox[2])} m (agora {br(nivel)} m). Chuva prevista na bacia: {f48:.0f} mm.")

    if os.environ.get("TESTE") == "1":
        sit = atual[1] if atual else "Normal"
        msgs.append(f"🧪 *Teste do monitor do rio*\nPassarela em *{br(nivel)} m* às {hora}{tend}. Situação: {sit}.")

    print(f"Passarela {br(nivel)} m às {hora}; cota: {estado['cota']}; {len(msgs)} aviso(s)")
    for m in msgs:
        enviar(m)
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(estado))


if __name__ == "__main__":
    main()
