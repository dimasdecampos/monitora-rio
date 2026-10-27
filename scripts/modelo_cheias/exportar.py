"""Gera public/paraitinga/modelo_cheias.json (pesos + desempenho no teste) para o painel.

Ordem para refazer o modelo do zero:
  python baixar_chuva.py   # chuva ERA5 horária da bacia (Open-Meteo), 2015 → hoje
  python baixar_prev.py    # previsões arquivadas (feitas 1 e 2 dias antes), 2024 → hoje
  python estat.py          # monta a tabela de casos (nível, chuva passada/futura, subida em 48 h)
  python logistico.py      # treina (2015–2021) e testa (2022–2026) o modelo de probabilidade
  python exportar.py       # avalia com a previsão real e grava o JSON do site
  python baixar_prev7.py   # previsões arquivadas feitas 1 a 7 dias antes
  python trajetoria.py     # linha de previsão por prazo (6 h a 7 dias), junta ao JSON do site
"""
import json, math
from datetime import date
from dados import AQUI, RAIZ, chuva_horaria, nivel_horario
from logistico import prob, feats

PONTOS = [(-23.22, -45.31), (-23.09, -45.19), (-23.07, -44.96), (-22.85, -44.85), (-22.95, -45.10)]
NOMES = ["São Luiz do Paraitinga", "Lagoinha", "Cunha", "Cabeceiras (Serra da Bocaina)", "Norte da bacia"]
COTA = 345

t, bacia, *_ = chuva_horaria()
pv = json.load(open(AQUI / "chuva_prevista.json")); idxp = {k[:13]: i for i, k in enumerate(pv["t"])}
w = json.load(open(AQUI / "pesos_logistico.json"))
niv = nivel_horario("58041000"); H = [niv[k][0] if k in niv else None for k in t]
N = len(t); ini = t.index("2024-02-01T00")

usaveis = [i for i in range(ini, N) if pv["d1"][idxp[t[i]]] is not None]
fator = sum(bacia[i] for i in usaveis) / sum(pv["d1"][idxp[t[i]]] for i in usaveis)
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
S = lambda a, b: acum[min(N, max(0, b))] - acum[min(N, max(0, a))]

def f48_prev(i):
    s = 0.0
    for h in range(1, 49):
        j = idxp.get(t[i + h]) if i + h < N else None
        v = pv["d1" if h <= 24 else "d2"][j] if j is not None else None
        if v is None: return None
        s += v
    return s * fator

def p_em(i):
    f = f48_prev(i)
    if f is None: return None
    l = dict(H0=H[i], p24=S(i - 24, i + 1), p72=S(i - 72, i + 1), api=S(i - 720, i - 72), f48=f)
    return prob(w["futuro"], l, COTA - H[i], True)

eventos = []
for i in range(ini + 48, N):
    if H[i] is not None and H[i] >= COTA and H[i - 1] is not None and H[i - 1] < COTA:
        if not eventos or i - eventos[-1] > 96: eventos.append(i)
avisos = {}
for lead in (6, 12, 24):
    n = 0
    for e in eventos:
        i = e - lead
        if H[i] is None or H[i] >= COTA: n += 1; continue
        p = p_em(i)
        if p is not None and p >= 0.3: n += 1
    avisos[lead] = n
dias, falsos = set(), set()
for i in range(ini, N - 48, 6):
    if H[i] is None or H[i] >= COTA: continue
    p = p_em(i)
    if p is not None and p >= 0.3:
        dias.add(t[i][:10])
        fut = [H[i + h] for h in range(1, 49) if H[i + h] is not None]
        if not fut or max(fut) < COTA: falsos.add(t[i][:10])

saida = {
    "versao": date.today().isoformat(),
    "estacao_referencia": "58041000",
    "descricao": "Probabilidade de o Rio Paraitinga em São Luiz subir pelo menos G cm nas próximas 48 h (regressão logística).",
    "pontos": [{"nome": n, "lat": la, "lon": lo} for n, (la, lo) in zip(NOMES, PONTOS)],
    "fator_previsao": round(fator, 3),
    "pesos": [round(x, 5) for x in w["futuro"]],
    "variaveis": ["1", "G/100", "ln(1+chuva prevista 48h)", "ln(1+chuva 24h)", "ln(1+chuva 72h)", "chuva 30 dias antes das últimas 72h / 100",
                  "nível atual (m)", "chuva prevista × solo", "chuva prevista × G", "chuva 24h × G", "G²"],
    "cotas_cm": {"atencao": 345, "alerta": 460, "inundacao": 510},
    # chuva dos últimos 30 dias na bacia (mm): limites de "seco", "úmido", "encharcado", "muito encharcado"
    "solo_mm": {"p33": 47, "p66": 130, "p90": 220},
    "teste": {
        "periodo": f"{t[ini][:7]} a {t[N - 1][:7]}",
        "cheias": len(eventos),
        "avisadas": {str(k): v for k, v in avisos.items()},
        "dias_com_aviso": len(dias),
        "dias_sem_cheia": len(falsos),
        "limiar_aviso": 0.3,
    },
}
destino = f"{RAIZ}/public/paraitinga/modelo_cheias.json"
try:  # mantém a linha de previsão gerada por trajetoria.py
    saida["trajetoria"] = json.load(open(destino, encoding="utf-8"))["trajetoria"]
except (OSError, KeyError):
    pass
json.dump(saida, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("gravado", destino)
print(json.dumps(saida["teste"], ensure_ascii=False))
# conferência: as variáveis precisam bater com logistico.feats
assert len(feats(dict(H0=200, p24=1, p72=1, api=1, f48=1), 100)) == len(saida["pesos"])
