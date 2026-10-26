"""Previsão do nível hora a hora (6 h a 7 dias) para a linha de previsão do gráfico.

Para cada prazo h, uma regressão linear estima a mudança de nível H(t+h) - H(t) a partir de:
nível atual, chuva passada (24 h, 72 h, 30 dias) e chuva no intervalo (t, t+h] e nas 24 h antes de t+h.
A incerteza vem dos erros do próprio modelo no treino (quantis por faixa de previsão).
Treino 2015–2021; teste 2022–2026 com a chuva que caiu e 2024–2026 com a previsão real da época.
"""
import json, math
from datetime import datetime
from dados import AQUI, RAIZ, chuva_horaria, nivel_horario

HORAS = [6, 12, 18, 24, 36, 48, 60, 72, 96, 120, 144, 168]
QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
FATOR = json.load(open(f"{RAIZ}/public/modelo_cheias.json", encoding="utf-8"))["fator_previsao"]

t, bacia, *_ = chuva_horaria()
niv = nivel_horario("58041000"); H = [niv[k][0] if k in niv else None for k in t]
N = len(t); fim_treino = t.index("2022-01-01T00")
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
S = lambda a, b: acum[min(N, max(0, b))] - acum[min(N, max(0, a))]


def variaveis(H0, p24, p72, api, r_tudo, r_fim, h):
    a, b, s = math.log1p(p24), math.log1p(p72), api / 100
    ra, rf, n = math.log1p(r_tudo), math.log1p(r_fim), H0 / 100
    return [1.0, n, n * n, a, b, s, ra, rf, ra * s, rf * s, ra * n, a * (24 / (h + 24))]


def resolver(A, y, ridge=1e-3):
    k = len(A[0]); M = [[0.0] * (k + 1) for _ in range(k)]
    for x, v in zip(A, y):
        for i in range(k):
            xi = x[i]
            Mi = M[i]
            for j in range(k): Mi[j] += xi * x[j]
            Mi[k] += xi * v
    for i in range(k): M[i][i] += ridge * len(A)
    for c in range(k):  # eliminação de Gauss
        p = max(range(c, k), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c] / M[c][c]
                for j in range(c, k + 1): M[r][j] -= f * M[c][j]
    return [M[i][k] / M[i][i] for i in range(k)]


def amostras(ini, fim, h, passo, chuva_futura):
    for i in range(max(ini, 720), min(fim, N - h), passo):
        if H[i] is None or H[i + h] is None: continue
        fut = chuva_futura(i, h)
        if fut is None: continue
        r_tudo, r_fim = fut
        yield variaveis(H[i], S(i - 24, i + 1), S(i - 72, i + 1), S(i - 720, i - 72), r_tudo, r_fim, h), H[i + h] - H[i], H[i]


perfeita = lambda i, h: (S(i + 1, i + h + 1), S(i + h - 23, i + h + 1))

# previsões arquivadas (feitas k dias antes)
pv = json.load(open(AQUI / "chuva_prevista7.json")); ipv = {k[:13]: j for j, k in enumerate(pv["t"])}
def real(i, h):
    dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d")
    serie = []
    for j in range(1, h + 1):
        k = ipv.get(t[i + j]) if i + j < N else None
        if k is None: return None
        lead = max(1, min(7, (datetime.strptime(t[i + j][:10], "%Y-%m-%d") - dia0).days))
        v = pv[f"d{lead}"][k]
        if v is None: return None
        serie.append(v * FATOR)
    return sum(serie), sum(serie[-24:])


def quantil(v, q): s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))]

modelo = {"horas": HORAS, "quantis": QS, "prazos": []}
print(f"{'prazo':>6} | {'MAE fica igual':>14} {'MAE c/ chuva real':>17} {'cobertura 10–90%':>16} | {'MAE c/ previsão':>15} {'cobertura':>9} | {'só subidas ≥0,5 m: igual / modelo / previsão':>44}")
for h in HORAS:
    tr = list(amostras(0, fim_treino, h, 3, perfeita))
    w = resolver([a for a, _, _ in tr], [y for _, y, _ in tr])
    pred = lambda x: sum(a * b for a, b in zip(w, x))
    # resíduos por faixa de mudança prevista
    pares = sorted((pred(x), y - pred(x)) for x, y, _ in tr)
    nb = 6; faixas = []
    for b in range(nb):
        bloco = pares[b * len(pares) // nb:(b + 1) * len(pares) // nb]
        faixas.append({"ate": bloco[-1][0] if b < nb - 1 else 1e9, "q": [round(quantil([r for _, r in bloco], q), 1) for q in QS]})
    def intervalo(p):
        f = next(f for f in faixas if p <= f["ate"]); return p + f["q"][1], p + f["q"][3], p + f["q"][5]

    def avaliar(casos):
        e_ig = e_mod = cob = 0; sub = [0, 0, 0]
        for x, y, h0 in casos:
            lo, md, hi = intervalo(pred(x))
            e_ig += abs(y); e_mod += abs(md - y); cob += lo <= y <= hi
            if y >= 50: sub[0] += 1; sub[1] += abs(y); sub[2] += abs(md - y)
        n = len(casos)
        return e_ig / n, e_mod / n, cob / n, (sub[1] / max(1, sub[0]), sub[2] / max(1, sub[0]), sub[0])

    te = list(amostras(fim_treino, N, h, 3, perfeita))
    ig, md, cob, sub = avaliar(te)
    ini_r = t.index("2024-02-01T00")
    rr = list(amostras(ini_r, N, h, 6, real))
    _, md_r, cob_r, sub_r = avaliar(rr)
    print(f"{h:5d}h | {ig/100:13.2f}m {md/100:16.2f}m {cob*100:15.0f}% | {md_r/100:14.2f}m {cob_r*100:8.0f}% | "
          f"{sub[0]/100:.2f} / {sub[1]/100:.2f} / {sub_r[1]/100:.2f} m (n={sub[2]}, {sub_r[2]})")
    modelo["prazos"].append({"h": h, "pesos": [round(v, 5) for v in w], "faixas": faixas,
                             "teste": {"mae_igual": round(ig, 1), "mae_modelo": round(md, 1), "mae_previsao": round(md_r, 1), "cobertura": round(cob_r, 2)}})

json.dump(modelo, open(AQUI / "trajetoria.json", "w"), indent=1)
print("gravado", AQUI / "trajetoria.json")

# junta ao arquivo do site
site = json.load(open(f"{RAIZ}/public/modelo_cheias.json", encoding="utf-8"))
site["trajetoria"] = modelo
json.dump(site, open(f"{RAIZ}/public/modelo_cheias.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("trajetória gravada em public/modelo_cheias.json")
