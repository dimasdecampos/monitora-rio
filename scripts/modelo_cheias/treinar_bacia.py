"""Treina a previsão de cheia (48 h e linha de 6 h a 7 dias) na régua principal de uma bacia
e grava public/<bacia>/<config.previsao.modelo> no mesmo formato usado pelo painel.

É a versão genérica de passarela.py + exportar_passarela.py (feitos para o Paraitinga):
  - nível horário da régua principal (histórico salvo);
  - chuva média na bacia (ERA5) nos config.pontos_chuva  -> dados/<config.chuva_era5.arquivo>;
  - previsões de chuva arquivadas (feitas 1 a 7 dias antes), 2024 → hoje -> dados/chuva_prevista7_<bacia>.json
    (baixadas na primeira vez; --baixar força de novo).
Só a versão A (nível + chuva). Treino até 2023 com a chuva que de fato caiu; teste de fev/2024
em diante com a previsão do tempo real da época. O modelo gravado é treinado com todos os dados.

Uso: python scripts/modelo_cheias/treinar_bacia.py --bacia paraibuna [--baixar]
"""
import argparse, json, math, random, sys, time, urllib.request
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import comum  # noqa: E402
import coletar  # noqa: E402

DADOS = AQUI / "dados"
GAPS = [15, 30, 50, 75, 100, 150, 200, 250]
HORAS = [6, 12, 18, 24, 36, 48, 60, 72, 96, 120, 144, 168]
QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]

a = argparse.ArgumentParser(); a.add_argument("--bacia", required=True); a.add_argument("--baixar", action="store_true")
ARGS = a.parse_args()
CFG = comum.config(ARGS.bacia); P = CFG["principal"]
PONTOS = [p for p in CFG["pontos_chuva"] if p.get("codigo")]
COTA = comum.estacoes(CFG)[P]["cotas_cm"]["atencao"]


# ---------------- dados ----------------
def baixar_previsoes(destino):
    lat = ",".join(str(p["lat"]) for p in PONTOS); lon = ",".join(str(p["lon"]) for p in PONTOS)
    cols = [f"precipitation_previous_day{k}" for k in range(1, 8)]
    saida = {"t": [], **{f"d{k}": [] for k in range(1, 8)}}
    hoje = date.today().isoformat()
    for ini, fim in [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", hoje)]:
        url = (f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&hourly={','.join(cols)}&start_date={ini}&end_date={fim}&timezone=America%2FSao_Paulo")
        for _ in range(4):
            try: d = json.load(urllib.request.urlopen(url, timeout=600)); break
            except Exception as e: print("erro", e); time.sleep(30)
        else: sys.exit("Open-Meteo não respondeu")
        d = d if isinstance(d, list) else [d]; tt = d[0]["hourly"]["time"]
        for k in range(1, 8):
            col = f"precipitation_previous_day{k}"
            for i in range(len(tt)):
                v = [r["hourly"][col][i] for r in d]
                saida[f"d{k}"].append(None if any(x is None for x in v) else sum(v) / len(v))
        saida["t"] += tt; print("previsões arquivadas", ini, fim, "ok")
    json.dump(saida, open(destino, "w"))


era5 = json.load(open(DADOS / CFG["chuva_era5"]["arquivo"]))
pts = CFG["chuva_era5"]["pontos"]
t = [x[:13] for x in era5[pts[0]]["t"]]
bacia = [sum((era5[p]["p"][i] or 0) for p in pts) / len(pts) for i in range(len(t))]
N = len(t); idx = {k: i for i, k in enumerate(t)}
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
S = lambda a, b: acum[min(N, max(0, b))] - acum[min(N, max(0, a))]

linhas = []
for f in sorted((comum.pasta(ARGS.bacia) / "historico" / P).glob("????-??.json")):
    linhas += json.load(open(f, encoding="utf-8"))["dados"]
nivel = {}
for tt_, n, _, _ in coletar.sem_picos_falsos(sorted(linhas)):
    if n is not None: nivel[tt_[:13]] = n          # última leitura de cada hora
H = [nivel.get(k) for k in t]

arq_prev = DADOS / f"chuva_prevista7_{ARGS.bacia}.json"
if ARGS.baixar or not arq_prev.exists(): baixar_previsoes(arq_prev)
pv = json.load(open(arq_prev)); ipv = {k[:13]: j for j, k in enumerate(pv["t"])}

# fator: quanto a chuva prevista para o dia seguinte precisa ser multiplicada para bater, em média, com a ERA5
soma_era5 = soma_prev = 0.0
for k, j in ipv.items():
    i = idx.get(k); v = pv["d1"][j]
    if i is not None and v is not None: soma_era5 += bacia[i]; soma_prev += v
FATOR = round(soma_era5 / soma_prev, 3) if soma_prev else 1.0
print(f"{ARGS.bacia}: régua {P}, {sum(h is not None for h in H)} horas de nível; chuva ERA5 até {t[-1]}; fator da previsão {FATOR}")


def f48_real(i):
    dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d"); s = 0.0
    for h in range(1, 49):
        j = ipv.get(t[i + h]) if i + h < N else None
        if j is None: return None
        lead = max(1, min(7, (datetime.strptime(t[i + h][:10], "%Y-%m-%d") - dia0).days))
        v = pv[f"d{lead}"][j]
        if v is None: return None
        s += v
    return s * FATOR


# ---------------- probabilidade de subir G cm em 48 h (versão A) ----------------
def vars_(c, G):
    f, a, b, s, g = math.log1p(c["f48"]), math.log1p(c["p24"]), math.log1p(c["p72"]), c["api"] / 100, G / 100
    return [1.0, g, f, a, b, s, c["H0"] / 100, f * s, f * g, a * g, g * g]


def treinar(casos, epocas=50, lr=.05, l2=1e-4):
    random.seed(1); dados = [(vars_(c, G), 1.0 if c["y"] >= G else 0.0) for c in casos for G in GAPS]
    w = [0.0] * len(dados[0][0]); m = [0.0] * len(w); v = [0.0] * len(w); passo = 0
    for _ in range(epocas):
        random.shuffle(dados)
        for k in range(0, len(dados), 256):
            lote = dados[k:k + 256]; grad = [0.0] * len(w)
            for x, y in lote:
                z = sum(p * q for p, q in zip(w, x)); pr = 1 / (1 + math.exp(-max(-30, min(30, z))))
                for j in range(len(w)): grad[j] += (pr - y) * x[j]
            passo += 1
            for j in range(len(w)):
                gj = grad[j] / len(lote) + l2 * w[j]
                m[j] = .9 * m[j] + .1 * gj; v[j] = .999 * v[j] + .001 * gj * gj
                w[j] -= lr * (m[j] / (1 - .9 ** passo)) / (math.sqrt(v[j] / (1 - .999 ** passo)) + 1e-8)
    return w


def prob(w, c, G):
    return 1 / (1 + math.exp(-max(-30, min(30, sum(p * q for p, q in zip(w, vars_(c, G)))))))


def montar(ini, fim, passo, chuva):
    out = []
    for i in range(max(720, idx.get(ini, 720)), min(idx.get(fim, N - 49), N - 49), passo):
        if H[i] is None: continue
        fut = [H[i + h] for h in range(1, 49) if H[i + h] is not None]
        if len(fut) < 40: continue
        f = S(i + 1, i + 49) if chuva == "perfeita" else f48_real(i)
        if f is None: continue
        out.append(dict(i=i, H0=H[i], p24=S(i - 24, i + 1), p72=S(i - 72, i + 1), api=S(i - 720, i - 72), f48=f,
                        y=max(fut) - H[i], pico=max(fut)))
    return out


def avaliar(w, casos):
    """Das vezes em que passou da atenção, quantas foram avisadas (chance ≥ 30%) 3/6/12/24 h antes."""
    por_i = {c["i"]: c for c in casos}
    eventos = []
    for i in range(1, N):
        if H[i] is not None and H[i - 1] is not None and H[i - 1] < COTA <= H[i] and (not eventos or i - eventos[-1] > 96):
            eventos.append(i)
    # os casos de teste vêm de 3 em 3 h: aceita o caso mais próximo (±1 h), como na contagem abaixo
    eventos = [e for e in eventos if any(e - L + d in por_i for L in (6, 12, 24) for d in (-1, 0, 1))]
    res = {}
    for L in (3, 6, 12, 24):
        ok = n = 0
        for e in eventos:
            c = por_i.get(e - L) or por_i.get(e - L - 1) or por_i.get(e - L + 1)
            if c is None: continue
            n += 1
            if c["H0"] >= COTA or prob(w, c, COTA - c["H0"]) >= .3: ok += 1
        res[L] = (ok, n)
    dias, falsos = set(), set()
    for c in casos:
        if c["H0"] < COTA and prob(w, c, COTA - c["H0"]) >= .3:
            dias.add(t[c["i"]][:10])
            if c["pico"] < COTA: falsos.add(t[c["i"]][:10])
    print("  " + " | ".join(f"{L:2d} h antes: {ok}/{n}" for L, (ok, n) in res.items()) + f" | dias com aviso {len(dias)}, sem cheia {len(falsos)}")
    return res, len(dias), len(falsos)


inicio = next(t[i] for i in range(720, N) if H[i] is not None)
inicio = max(inicio, "2015-01-01T00")
w_teste = treinar(montar(inicio, "2024-01-01T00", 6, "perfeita"))
teste = montar("2024-02-01T00", t[-60], 3, "real")
print(f"teste fev/2024 → {t[-60][:10]} com a previsão do tempo real ({len(teste)} casos), cota de atenção {COTA / 100:.2f} m:")
res, dias, falsos = avaliar(w_teste, teste)
w_final = treinar(montar(inicio, t[-60], 6, "perfeita"))


# ---------------- linha de previsão por prazo ----------------
def resolver(A, y, ridge=1e-3):
    k = len(A[0]); Mx = [[0.0] * (k + 1) for _ in range(k)]
    for x, v in zip(A, y):
        for i in range(k):
            xi = x[i]; Mi = Mx[i]
            for j in range(k): Mi[j] += xi * x[j]
            Mi[k] += xi * v
    for i in range(k): Mx[i][i] += ridge * len(A)
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(Mx[r][c])); Mx[c], Mx[p] = Mx[p], Mx[c]
        for r in range(k):
            if r != c and Mx[r][c]:
                f = Mx[r][c] / Mx[c][c]
                for j in range(c, k + 1): Mx[r][j] -= f * Mx[c][j]
    return [Mx[i][k] / Mx[i][i] for i in range(k)]


def variaveis(H0, p24, p72, api, ra, rf, h):
    a_, b_, s = math.log1p(p24), math.log1p(p72), api / 100
    ra, rf, n = math.log1p(ra), math.log1p(rf), H0 / 100
    return [1.0, n, n * n, a_, b_, s, ra, rf, ra * s, rf * s, ra * n, a_ * (24 / (h + 24)), 0.0]   # último termo: régua rio acima (não usada)


def amostras(ini, fim, h, passo, real):
    for i in range(max(720, idx.get(ini, 720)), min(idx.get(fim, N - h - 1), N - h - 1), passo):
        if H[i] is None or H[i + h] is None: continue
        if real:
            dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d"); serie = []
            for j in range(1, h + 1):
                k = ipv.get(t[i + j])
                if k is None: serie = None; break
                lead = max(1, min(7, (datetime.strptime(t[i + j][:10], "%Y-%m-%d") - dia0).days))
                v = pv[f"d{lead}"][k]
                if v is None: serie = None; break
                serie.append(v * FATOR)
            if serie is None: continue
            ra, rf = sum(serie), sum(serie[-24:])
        else:
            ra, rf = S(i + 1, i + h + 1), S(i + h - 23, i + h + 1)
        yield variaveis(H[i], S(i - 24, i + 1), S(i - 72, i + 1), S(i - 720, i - 72), ra, rf, h), H[i + h] - H[i]


def quantil(v, q): s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))]


def ajustar(ini, fim, h):
    tr = list(amostras(ini, fim, h, 3, False))
    A = [x[:-1] for x, _ in tr]   # sem a coluna da régua rio acima (sempre 0)
    w = resolver(A, [y for _, y in tr]) + [0.0]
    pred = lambda x: sum(p * q for p, q in zip(w, x))
    pares = sorted((pred(x), y - pred(x)) for x, y in tr); faixas = []
    for b in range(6):
        bloco = pares[b * len(pares) // 6:(b + 1) * len(pares) // 6]
        faixas.append({"ate": bloco[-1][0] if b < 5 else 1e9, "q": [round(quantil([r for _, r in bloco], q), 1) for q in QS]})
    return w, faixas, pred


traj = {"horas": HORAS, "quantis": QS, "prazos": []}
print("\nlinha de previsão (treino até 2023, teste 2024 → hoje com a previsão real):")
for h in HORAS:
    w, faixas, pred = ajustar(inicio, "2024-01-01T00", h)
    te = list(amostras("2024-02-01T00", t[-60], h, 6, True))
    def faixa(p): f = next(f for f in faixas if p <= f["ate"]); return p + f["q"][1], p + f["q"][3], p + f["q"][5]
    e_ig = sum(abs(y) for _, y in te) / len(te)
    e_md = sum(abs(faixa(pred(x))[1] - y) for x, y in te) / len(te)
    cob = sum(faixa(pred(x))[0] <= y <= faixa(pred(x))[2] for x, y in te) / len(te)
    print(f"  {h:4d} h: erro médio {e_md:5.1f} cm (se ficar igual: {e_ig:5.1f}) | faixa 10–90% acertou {cob * 100:3.0f}%")
    wf, ff, _ = ajustar(inicio, t[-60], h)
    traj["prazos"].append({"h": h, "pesos": [round(v, 5) for v in wf], "faixas": ff,
                           "teste": {"mae_igual": round(e_ig, 1), "mae_previsao": round(e_md, 1), "cobertura": round(cob, 2)}})

# solo: chuva dos 30 dias anteriores (api + 72 h) nos casos de treino, em tercis e p90
solos = sorted(S(i - 720, i - 72) + S(i - 72, i + 1) for i in range(720, N, 24))
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
fim_teste = datetime.strptime(t[-60][:7], "%Y-%m")
saida = {
    "versao": datetime.now().date().isoformat(),
    "estacao_referencia": P,
    "descricao": f"Probabilidade de o {CFG['rio']} em {CFG['cidade']} subir pelo menos G cm nas próximas 48 h (regressão logística).",
    "pontos": [{"nome": p["nome"], "lat": p["lat"], "lon": p["lon"]} for p in PONTOS],
    "fator_previsao": FATOR,
    "solo_mm": {"p33": round(quantil(solos, .33)), "p66": round(quantil(solos, .66)), "p90": round(quantil(solos, .9))},
    "cotas_cm": comum.estacoes(CFG)[P]["cotas_cm"],
    "passarela": {   # nome da chave mantido por compatibilidade com o painel
        "versao": datetime.now().date().isoformat(), "estacao": P,
        "descricao": f"Probabilidade de a régua {P} subir pelo menos G cm em 48 h: nível + chuva na bacia (passada e prevista).",
        "pesos_A": [round(x, 5) for x in w_final],
        "teste": {"periodo": f"fev/2024 a {MESES[fim_teste.month - 1]}/{fim_teste.year}", "cheias": res[6][1],
                  "avisadas": {str(L): ok for L, (ok, n) in res.items()},
                  "dias_com_aviso": dias, "dias_sem_cheia": falsos, "limiar_aviso": 0.3},
        "trajetoria": traj,
    },
}
destino = comum.pasta(ARGS.bacia) / CFG["previsao"]["modelo"]
json.dump(saida, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\ngravado em", destino.relative_to(comum.RAIZ))
