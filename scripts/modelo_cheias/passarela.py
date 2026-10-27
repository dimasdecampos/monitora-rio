"""Previsão de cheia na régua da Passarela (SP Águas), com as réguas rio acima.

Compara três versões do modelo de probabilidade (subir pelo menos G cm em 48 h):
  A: nível da Passarela + chuva na bacia (passada e prevista)        — treino 2018–2023
  B: A + régua de Cunha (subida nas últimas horas)                   — treino 2020–2023
  C: B + régua de Lagoinha (Barro Vermelho)                          — treino 2024–2025
Teste com a previsão do tempo real da época (2024–2026 para A e B; 2025-07 a 2026-10 para C).

Uso: python passarela.py   (depois de baixar_chuva.py e baixar_prev7.py)
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
                hl=HL[i], hc=HC[i])


def vars_(c, G, versao):
    f, a, b, s, g = math.log1p(c["f48"]), math.log1p(c["p24"]), math.log1p(c["p72"]), c["api"] / 100, G / 100
    x = [1.0, g, f, a, b, s, c["H0"] / 100, f * s, f * g, a * g, g * g]
    if versao in ("B", "C"):
        dc = (c["dc6"] or 0) / 100; dc12 = (c["dc12"] or 0) / 100
        x += [max(dc, 0), max(dc12, 0), max(dc, 0) / (g + .3)]
    if versao == "C":
        dl = (c["dl6"] or 0) / 100; dl3 = (c["dl3"] or 0) / 100
        x += [max(dl, 0), max(dl3, 0), max(dl, 0) / (g + .3), (c["hl"] or 0) / 100]
    return x


def treinar(casos, versao, epocas=50, lr=.05, l2=1e-4):
    random.seed(1); dados = []
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
    eventos = [e for e in eventos if any(e - L in por_i for L in (6, 12, 24))]
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
    print("Passarela: horas com dado", sum(h is not None for h in H), "| Cunha", sum(h is not None for h in HC), "| Lagoinha", sum(h is not None for h in HL))
    modelos = {}
    tr_A = montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", [])
    tr_B = montar("2020-01-01T00", "2024-01-01T00", 6, "perfeita", ["dc6", "dc12"])
    print("casos de treino A", len(tr_A), "B", len(tr_B))
    modelos["A"] = treinar(tr_A, "A"); modelos["B"] = treinar(tr_B, "B")
    te = montar("2024-02-01T00", "2026-10-24T00", 3, "real", [])
    te_B = [c for c in te if c["dc6"] is not None and c["dc12"] is not None]
    print(f"\nTeste fev/2024–out/2026 com a previsão do tempo real ({len(te)} casos; {len(te_B)} com Cunha):")
    avaliar(modelos["A"], "A", te, "A: Passarela + chuva")
    avaliar(modelos["A"], "A", te_B, "A (mesmos casos de B)")
    avaliar(modelos["B"], "B", te_B, "B: + Cunha")

    tr_C = montar("2024-03-01T00", "2025-07-01T00", 3, "real", ["dc6", "dc12", "dl3", "dl6", "hl"])
    te_C = montar("2025-07-01T00", "2026-10-24T00", 3, "real", ["dc6", "dc12", "dl3", "dl6", "hl"])
    print(f"\nTeste jul/2025–out/2026 ({len(te_C)} casos com Cunha e Lagoinha; treino C: {len(tr_C)} casos de 2024–2025):")
    if tr_C:
        modelos["C"] = treinar(tr_C, "C")
        avaliar(modelos["A"], "A", te_C, "A: Passarela + chuva")
        avaliar(modelos["B"], "B", te_C, "B: + Cunha")
        avaliar(modelos["C"], "C", te_C, "C: + Cunha + Lagoinha")
    json.dump(modelos, open(AQUI / "pesos_passarela.json", "w"))
