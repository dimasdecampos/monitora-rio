import json, math
from dados import AQUI, chuva_horaria, nivel_horario
from logistico import prob, COTAS
t, bacia, *_ = chuva_horaria()
pv = json.load(open(AQUI / "chuva_prevista.json")); idxp = {k[:13]: i for i, k in enumerate(pv["t"])}
w = json.load(open(AQUI / "pesos_logistico.json"))
niv = nivel_horario("58041000"); H = [niv[k][0] if k in niv else None for k in t]
N = len(t); ini = t.index("2024-02-01T00")
# fator de correção: a previsão chove menos que o ERA5 no total
tot_e = sum(bacia[i] for i in range(ini, N) if pv["d1"][idxp[t[i][:13]]] is not None)
tot_p = sum(pv["d1"][idxp[t[i][:13]]] for i in range(ini, N) if pv["d1"][idxp[t[i][:13]]] is not None)
fator = tot_e / tot_p
print(f"ERA5 {tot_e:.0f} mm x previsão {tot_p:.0f} mm no mesmo período -> fator {fator:.2f}")
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
S = lambda a, b: acum[min(N, max(0, b))] - acum[min(N, max(0, a))]
def f48_prev(i):
    s = 0.0
    for h in range(1, 49):
        j = idxp.get(t[i + h][:13]) if i + h < N else None
        v = pv["d1" if h <= 24 else "d2"][j] if j is not None else None
        if v is None: return None
        s += v
    return s * fator
def linha(i, f48):
    return dict(H0=H[i], p24=S(i - 24, i + 1), p72=S(i - 72, i + 1), api=S(i - 720, i - 72), f48=f48)
COTA = 345
# eventos: momentos em que o nível cruza 345 vindo de baixo (separados por 4 dias)
eventos = []
for i in range(ini + 48, N):
    if H[i] is not None and H[i] >= COTA and H[i - 1] is not None and H[i - 1] < COTA:
        if not eventos or i - eventos[-1] > 96: eventos.append(i)
print(f"\n{len(eventos)} vezes em que o rio passou da cota de atenção (fev/2024–out/2026)")
for nome, usar in (("previsão do tempo real (Open-Meteo, 1–2 dias antes)", "real"), ("chuva perfeita (o que de fato caiu)", "perfeita"), ("sem previsão (só chuva passada)", "passado")):
    res = {6: 0, 12: 0, 24: 0}
    for e in eventos:
        for lead in res:
            i = e - lead
            if H[i] is None or H[i] >= COTA: res[lead] += 1; continue   # já estava acima: conta como avisado
            f = f48_prev(i) if usar == "real" else S(i + 1, i + 49)
            if f is None: continue
            p = prob(w["passado" if usar == "passado" else "futuro"], linha(i, f), COTA - H[i], usar != "passado")
            if p >= 0.3: res[lead] += 1
    # alarmes falsos: dias com p>=0.3 (checado a cada 6h) sem cruzamento nas 48h seguintes
    dias_alarme, dias_falsos = set(), set()
    for i in range(ini, N - 48, 6):
        if H[i] is None or H[i] >= COTA: continue
        f = f48_prev(i) if usar == "real" else S(i + 1, i + 49)
        if f is None: continue
        p = prob(w["passado" if usar == "passado" else "futuro"], linha(i, f), COTA - H[i], usar != "passado")
        if p >= 0.3:
            dias_alarme.add(t[i][:10])
            fut = [H[i + h] for h in range(1, 49) if H[i + h] is not None]
            if not fut or max(fut) < COTA: dias_falsos.add(t[i][:10])
    print(f"\n  {nome}")
    print("   avisou com antecedência: " + " | ".join(f"{l} h antes: {v}/{len(eventos)}" for l, v in res.items()))
    print(f"   dias com aviso (≥30%): {len(dias_alarme)}, dos quais sem cheia em 48 h: {len(dias_falsos)}")
