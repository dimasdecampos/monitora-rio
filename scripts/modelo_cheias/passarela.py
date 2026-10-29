"""Previsão de cheia na régua da Passarela (SP Águas), com as réguas rio acima.

Compara as versões do modelo de probabilidade (subir pelo menos G cm em 48 h):
  A:  nível da Passarela + chuva na bacia (ERA5, passada e prevista)        — treino 2018–2023
  B:  A + régua de Cunha (subida nas últimas horas)                         — treino 2020–2023
  P:  A + pluviômetro de Barro Vermelho, em Lagoinha (chuva medida 6–72 h)  — treino 2018–2023
  BP: B + pluviômetro de Barro Vermelho
Teste com a previsão do tempo real da época (fev/2024 a out/2026). A chuva da ERA5 vê menos da metade
dos temporais; o pluviômetro, rio acima (~10 h até a cidade), mede a chuva de verdade.

Uso: python passarela.py   (depois de baixar_chuva.py, baixar_prev7.py e baixar_pluviometro.py)
"""
import json, math, random, glob
from datetime import datetime, timedelta
from dados import AQUI, RAIZ, chuva_horaria, c as coletar

GAPS = [15, 30, 50, 75, 100, 150, 200, 250]


def serie_sp(cod):
    """Nível horário (cm) de uma régua da SP Águas a partir do histórico salvo."""
    linhas = []
    for f in sorted(glob.glob(f"{RAIZ}/public/paraitinga/historico/{cod}/????-??.json")):
        linhas += json.load(open(f))["dados"]
    linhas = coletar.sem_picos_falsos(sorted(linhas))
    return {t[:13]: n for t, n, _, _ in linhas if n is not None}


t, bacia, *_ = chuva_horaria()
N = len(t); idx = {k: i for i, k in enumerate(t)}
P = serie_sp("sp664"); CUNHA = serie_sp("sp818"); LAG = serie_sp("sp662")
H = [P.get(k) for k in t]; HC = [CUNHA.get(k) for k in t]; HL = [LAG.get(k) for k in t]
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
S = lambda a, b: acum[min(N, max(0, b))] - acum[min(N, max(0, a))]



def pluviometro(cod="sp662"):
    """Chuva por hora (mm) do pluviômetro: anos antigos (baixar_pluviometro.py) + histórico do site.
    Meses com menos de 0,5 mm são tratados como aparelho parado (o de Barro Vermelho gravou zeros em 2015)."""
    h = {}
    antigo = AQUI / f"pluv_{cod}.json"
    if antigo.exists(): h.update(json.load(open(antigo)))
    for f in sorted(glob.glob(f"{RAIZ}/public/paraitinga/historico/{cod}/????-??.json")):
        for t_, _, _, ch in json.load(open(f))["dados"]:
            if ch is not None: h[t_[:13]] = h.get(t_[:13], 0) + ch
    h = {k: v for k, v in h.items() if 0 <= v <= 120}          # leituras absurdas
    por_mes = {}
    for k, v in h.items(): por_mes[k[:7]] = por_mes.get(k[:7], 0) + v
    return {k: v for k, v in h.items() if por_mes[k[:7]] >= 0.5}


def janelas(serie):
    """Soma da chuva entre as horas i e j (exclusive); None se faltar mais de 10% das horas."""
    tem = [k in serie for k in t]; a = [0.0]; ok = [0]
    for k, x in zip(t, tem): a.append(a[-1] + serie.get(k, 0)); ok.append(ok[-1] + x)
    def soma(i, j):
        i, j = max(0, i), min(N, j)
        return None if j <= i or ok[j] - ok[i] < 0.9 * (j - i) else a[j] - a[i]
    return soma


PL = janelas(pluviometro())
pv = json.load(open(AQUI / "chuva_prevista7.json")); ipv = {k[:13]: j for j, k in enumerate(pv["t"])}
FATOR = json.load(open(f"{RAIZ}/public/paraitinga/modelo_cheias.json", encoding="utf-8"))["fator_previsao"]


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


def dif(serie, i, h):
    a, b = serie[i], serie[i - h] if i >= h else None
    return None if a is None or b is None else a - b


def caso(i, f48):
    """Variáveis disponíveis na hora i (None quando a régua não tem dado)."""
    if H[i] is None: return None
    return dict(i=i, H0=H[i], p24=S(i - 24, i + 1), p72=S(i - 72, i + 1), api=S(i - 720, i - 72), f48=f48,
                dc6=dif(HC, i, 6), dc12=dif(HC, i, 12), dl3=dif(HL, i, 3), dl6=dif(HL, i, 6),
                hl=HL[i], hc=HC[i], l6=PL(i - 6, i + 1), l12=PL(i - 12, i + 1), l24=PL(i - 24, i + 1), l72=PL(i - 72, i + 1))

PLUV = ["l6", "l12", "l24", "l72"]   # variáveis do pluviômetro (versões P e BP)


def vars_(c, G, versao):
    f, a, b, s, g = math.log1p(c["f48"]), math.log1p(c["p24"]), math.log1p(c["p72"]), c["api"] / 100, G / 100
    x = [1.0, g, f, a, b, s, c["H0"] / 100, f * s, f * g, a * g, g * g]
    if "B" in versao:
        dc = (c["dc6"] or 0) / 100; dc12 = (c["dc12"] or 0) / 100
        x += [max(dc, 0), max(dc12, 0), max(dc, 0) / (g + .3)]
    if "P" in versao:   # mesma ordem no painel e em alertas.py
        L = math.log1p
        x += [L(c["l6"]), L(c["l24"]), L(c["l72"]), L(c["l24"]) * g, L(c["l12"]) * g]
    return x


def treinar(casos, versao, epocas=50, lr=.05, l2=1e-4, semente=1):
    random.seed(semente); dados = []
    for c in casos:
        for G in GAPS: dados.append((vars_(c, G, versao), 1.0 if c["y"] >= G else 0.0))
    w = [0.0] * len(dados[0][0]); m = [0.0] * len(w); v = [0.0] * len(w); passo = 0
    for _ in range(epocas):
        random.shuffle(dados)
        for k in range(0, len(dados), 256):
            lote = dados[k:k + 256]; grad = [0.0] * len(w)
            for x, y in lote:
                z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-max(-30, min(30, z))))
                for j in range(len(w)): grad[j] += (p - y) * x[j]
            passo += 1
            for j in range(len(w)):
                gj = grad[j] / len(lote) + l2 * w[j]
                m[j] = .9 * m[j] + .1 * gj; v[j] = .999 * v[j] + .001 * gj * gj
                w[j] -= lr * (m[j] / (1 - .9 ** passo)) / (math.sqrt(v[j] / (1 - .999 ** passo)) + 1e-8)
    return w


def treinar_media(casos, versao, n=5):
    """Média dos pesos de n treinos com sorteios diferentes: um treino só varia muito (de 7 a 12
    cheias avisadas com 12 h no teste, só pelo sorteio)."""
    ws = [treinar(casos, versao, semente=s) for s in range(1, n + 1)]
    return [sum(w[j] for w in ws) / n for j in range(len(ws[0]))]


def prob(w, c, G, versao):
    return 1 / (1 + math.exp(-max(-30, min(30, sum(a * b for a, b in zip(w, vars_(c, G, versao)))))))


def montar(ini, fim, passo, chuva, exige):
    out = []
    for i in range(max(720, idx.get(ini, 720)), min(idx.get(fim, N - 49), N - 49), passo):
        fut = [H[i + h] for h in range(1, 49) if H[i + h] is not None]
        if len(fut) < 40: continue
        f = S(i + 1, i + 49) if chuva == "perfeita" else f48_real(i)
        if f is None: continue
        c = caso(i, f)
        if c is None or any(c[k] is None for k in exige): continue
        c["y"] = max(fut) - c["H0"]; c["pico"] = max(fut)
        out.append(c)
    return out


COTA = 191.9   # atenção oficial na Passarela


def avaliar(w, versao, casos, rotulo):
    """Por evento: das vezes em que passou da atenção, quantas foram avisadas (p ≥ 30%) 6/12/24 h antes."""
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
            if c["H0"] >= COTA or prob(w, c, COTA - c["H0"], versao) >= .3: ok += 1
        res[L] = (ok, n)
    dias, falsos = set(), set()
    for c in casos:
        if c["H0"] < COTA and prob(w, c, COTA - c["H0"], versao) >= .3:
            dias.add(t[c["i"]][:10])
            if c["pico"] < COTA: falsos.add(t[c["i"]][:10])
    print(f"  {rotulo:44s} " + " | ".join(f"{L:2d} h antes: {ok}/{n}" for L, (ok, n) in res.items())
          + f" | dias com aviso {len(dias)}, sem cheia {len(falsos)}")
    return res, len(dias), len(falsos)


if __name__ == "__main__":
    print("Passarela: horas com dado", sum(h is not None for h in H), "| Cunha", sum(h is not None for h in HC),
          "| pluviômetro de Barro Vermelho", sum(PL(i, i + 1) is not None for i in range(N)))
    te = montar("2024-02-01T00", "2026-10-24T00", 3, "real", PLUV)
    te_B = [c for c in te if c["dc6"] is not None and c["dc12"] is not None]
    modelos = {}
    for v, ini, exige in (("A", "2018-01-01T00", []), ("P", "2018-01-01T00", PLUV),
                          ("B", "2020-01-01T00", ["dc6", "dc12"]), ("BP", "2020-01-01T00", ["dc6", "dc12"] + PLUV)):
        tr = montar(ini, "2024-01-01T00", 6, "perfeita", exige)
        print(f"treinando {v} ({len(tr)} casos)", flush=True)
        modelos[v] = treinar_media(tr, v)
    print(f"\nTeste fev/2024–out/2026 com a previsão do tempo real, só horas com o pluviômetro transmitindo ({len(te)} casos):")
    avaliar(modelos["A"], "A", te, "A: Passarela + chuva")
    avaliar(modelos["P"], "P", te, "P: + pluviômetro de Barro Vermelho")
    print(f"\nSó horas com Cunha transmitindo ({len(te_B)} casos):")
    for v, r in (("A", "A"), ("P", "P"), ("B", "B: + Cunha"), ("BP", "BP: + Cunha + pluviômetro")):
        avaliar(modelos[v], v, te_B, r)
    json.dump(modelos, open(AQUI / "pesos_passarela.json", "w"))
