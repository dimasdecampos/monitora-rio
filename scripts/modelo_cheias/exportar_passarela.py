"""Treina os modelos finais na régua da Passarela e grava em public/modelo_cheias.json (chave "passarela").

- Probabilidade de subir G cm em 48 h: versão A (Passarela + chuva) e B (+ subida da régua de Cunha).
- Linha de previsão por prazo (6 h a 7 dias) na Passarela.
O desempenho mostrado no site vem de modelos treinados só até 2023 e testados em 2024–2026
com a previsão do tempo real; os modelos gravados são treinados com todos os dados.
"""
import json, math
from datetime import datetime
import passarela as M

HORAS = [6, 12, 18, 24, 36, 48, 60, 72, 96, 120, 144, 168]
QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]


def resolver(A, y, ridge=1e-3):
    """Mínimos quadrados com regularização leve (eliminação de Gauss)."""
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

# ---------------- probabilidade ----------------
treino_A = M.montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", [])
treino_B = M.montar("2020-01-01T00", "2024-01-01T00", 6, "perfeita", ["dc6", "dc12"])
wA, wB = M.treinar(treino_A, "A"), M.treinar(treino_B, "B")
teste = M.montar("2024-02-01T00", "2026-10-24T00", 3, "real", [])
teste_B = [c for c in teste if c["dc6"] is not None and c["dc12"] is not None]
print("teste (modelos treinados até 2023, previsão real):")
resA, diasA, falsosA = M.avaliar(wA, "A", teste, "A")
resB, diasB, falsosB = M.avaliar(wB, "B", teste_B, "B")

fim = M.t[-60][:13]
wA_final = M.treinar(M.montar("2018-01-01T00", fim, 6, "perfeita", []), "A")
wB_final = M.treinar(M.montar("2020-01-01T00", fim, 6, "perfeita", ["dc6", "dc12"]), "B")

# ---------------- linha de previsão por prazo ----------------
H, S, N, t = M.H, M.S, M.N, M.t
def variaveis(H0, p24, p72, api, ra, rf, h, dc):
    a, b, s = math.log1p(p24), math.log1p(p72), api / 100
    ra, rf, n = math.log1p(ra), math.log1p(rf), H0 / 100
    d = max(dc or 0, 0) / 100
    return [1.0, n, n * n, a, b, s, ra, rf, ra * s, rf * s, ra * n, a * (24 / (h + 24)), d * (24 / (h + 24))]

def amostras(ini, fim, h, passo, real):
    i0, i1 = M.idx.get(ini, 720), M.idx.get(fim, N - h - 1)
    for i in range(max(720, i0), min(i1, N - h - 1), passo):
        if H[i] is None or H[i + h] is None: continue
        if real:
            dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d"); serie = []
            for j in range(1, h + 1):
                k = M.ipv.get(t[i + j])
                if k is None: serie = None; break
                lead = max(1, min(7, (datetime.strptime(t[i + j][:10], "%Y-%m-%d") - dia0).days))
                v = M.pv[f"d{lead}"][k]
                if v is None: serie = None; break
                serie.append(v * M.FATOR)
            if serie is None: continue
            ra, rf = sum(serie), sum(serie[-24:])
        else:
            ra, rf = S(i + 1, i + h + 1), S(i + h - 23, i + h + 1)
        yield variaveis(H[i], S(i - 24, i + 1), S(i - 72, i + 1), S(i - 720, i - 72), ra, rf, h, M.dif(M.HC, i, 6)), H[i + h] - H[i]

def quantil(v, q): s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))]

def ajustar(ini, fim, h):
    tr = list(amostras(ini, fim, h, 3, False))
    w = resolver([a for a, _ in tr], [y for _, y in tr])
    pred = lambda x: sum(a * b for a, b in zip(w, x))
    pares = sorted((pred(x), y - pred(x)) for x, y in tr); faixas = []
    for b in range(6):
        bloco = pares[b * len(pares) // 6:(b + 1) * len(pares) // 6]
        faixas.append({"ate": bloco[-1][0] if b < 5 else 1e9, "q": [round(quantil([r for _, r in bloco], q), 1) for q in QS]})
    return w, faixas, pred

traj = {"horas": HORAS, "quantis": QS, "prazos": []}
print("\nlinha de previsão (treino até 2023, teste 2024–2026 com previsão real):")
for h in HORAS:
    w, faixas, pred = ajustar("2018-01-01T00", "2024-01-01T00", h)
    te = list(amostras("2024-02-01T00", "2026-10-24T00", h, 6, True))
    def faixa(p): f = next(f for f in faixas if p <= f["ate"]); return p + f["q"][1], p + f["q"][3], p + f["q"][5]
    e_ig = sum(abs(y) for _, y in te) / len(te)
    e_md = sum(abs(faixa(pred(x))[1] - y) for x, y in te) / len(te)
    cob = sum(faixa(pred(x))[0] <= y <= faixa(pred(x))[2] for x, y in te) / len(te)
    print(f"  {h:4d} h: erro médio {e_md:5.1f} cm (fica igual: {e_ig:5.1f}) | faixa 10–90% acertou {cob*100:3.0f}%")
    wf, ff, _ = ajustar("2018-01-01T00", fim, h)
    traj["prazos"].append({"h": h, "pesos": [round(v, 5) for v in wf], "faixas": ff,
                           "teste": {"mae_igual": round(e_ig, 1), "mae_previsao": round(e_md, 1), "cobertura": round(cob, 2)}})

destino = f"{M.RAIZ}/public/modelo_cheias.json"
site = json.load(open(destino, encoding="utf-8"))
site["passarela"] = {
    "versao": datetime.now().date().isoformat(),
    "estacao": "sp664",
    "descricao": "Probabilidade de a Passarela subir pelo menos G cm em 48 h. A: nível + chuva na bacia; B: A + subida da régua de Cunha (6 h e 12 h).",
    "pesos_A": [round(x, 5) for x in wA_final],
    "pesos_B": [round(x, 5) for x in wB_final],
    "teste": {
        "periodo": "fev/2024 a out/2026", "cheias": resA[6][1],
        "avisadas": {str(L): ok for L, (ok, n) in resA.items()},
        "dias_com_aviso": diasA, "dias_sem_cheia": falsosA,
        "B_dias_com_aviso": diasB, "B_dias_sem_cheia": falsosB, "limiar_aviso": 0.3,
    },
    "trajetoria": traj,
}
json.dump(site, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\ngravado em", destino)
