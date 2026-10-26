"""Testa previsões de 48 h como se fossem feitas na época (2022–2026, fora da calibração)."""
import json, math, sys, bisect
import modelo as M

fonte = M.FONTE
p = json.load(open(AQUI / f"param_{M.ESTACAO}_{fonte}.json"))["p"]
P = M.P
COTA = 345  # atenção na régua da CESP

# ---- simulação guardando os estados de cada hora ----
def simular_estados(p, P):
    dw, c0, c1, k1, k2, area, fb, k3, qb0, lag = p
    kw = math.exp(-1 / (24 * dw)); lag = int(round(lag))
    W = S1 = S2 = 0.0; S3 = qb0 * k3 / max(area, 1e-6)
    est, Qs = [], []
    for i in range(len(P)):
        est.append((W, S1, S2, S3))
        pi = P[i - lag] if i >= lag else 0.0
        W = W * kw + pi
        c = min(1, max(0, c0 + c1 * W / 100)); r = c * pi
        S1 += r * (1 - fb); q1 = S1 / k1; S1 -= q1
        S2 += q1; q2 = S2 / k2; S2 -= q2
        S3 += r * fb; q3 = S3 / k3; S3 -= q3
        Qs.append(area * (q2 + q3) + qb0)
    return est, Qs

def prever(p, estado, chuva_passada, chuva_futura):
    """Roda 48 h a partir do estado. chuva_passada cobre o atraso (lag)."""
    dw, c0, c1, k1, k2, area, fb, k3, qb0, lag = p
    kw = math.exp(-1 / (24 * dw)); lag = int(round(lag))
    W, S1, S2, S3 = estado
    serie = chuva_passada + chuva_futura
    out = []
    for h in range(len(chuva_futura)):
        pi = serie[len(chuva_passada) + h - lag]
        W = W * kw + pi
        c = min(1, max(0, c0 + c1 * W / 100)); r = c * pi
        S1 += r * (1 - fb); q1 = S1 / k1; S1 -= q1
        S2 += q1; q2 = S2 / k2; S2 -= q2
        S3 += r * fb; q3 = S3 / k3; S3 -= q3
        out.append(area * (q2 + q3) + qb0)
    return out

# ---- curva-chave (vazão -> nível) a partir dos pares observados recentes ----
pares = sorted((M.Q[i], M.H[i]) for i in range(M.fim_calib - 20000, M.N) if M.Q[i] is not None and M.H[i] is not None)
nb = 300
tab = []
for b in range(nb):
    bloco = pares[b * len(pares) // nb:(b + 1) * len(pares) // nb]
    if bloco: tab.append((sum(q for q, _ in bloco) / len(bloco), sorted(h for _, h in bloco)[len(bloco) // 2]))
qs, hs = [], []
for q, h in tab:
    if not hs or (q > qs[-1] and h >= hs[-1]): qs.append(q); hs.append(h)
def nivel_de(q):
    if q <= qs[0]: return hs[0] - (qs[0] - q) * (hs[1] - hs[0]) / max(qs[1] - qs[0], 1e-6)
    if q >= qs[-1]:  # extrapola com a inclinação do fim da curva
        k = max(1, len(qs) // 20)
        return hs[-1] + (q - qs[-1]) * (hs[-1] - hs[-1 - k]) / max(qs[-1] - qs[-1 - k], 1e-6)
    j = bisect.bisect(qs, q)
    return hs[j - 1] + (q - qs[j - 1]) * (hs[j] - hs[j - 1]) / (qs[j] - qs[j - 1])

if __name__ == "__main__":
    est, Qs = simular_estados(p, P)
    lag = int(round(p[9]))
    resultados = {}
    for tau in (12, 24, 48, 96):
        casos = []
        for i in range(M.fim_calib, M.N - 48, 3):
            if M.H[i] is None or M.Q[i] is None: continue
            fut = [M.H[i + h] for h in range(1, 49)]
            if sum(v is None for v in fut) > 8: continue
            obs_pico = max(v for v in fut if v is not None)
            erro = M.Q[i] - Qs[i]
            desvio_h = M.H[i] - nivel_de(M.Q[i])
            prev = {}
            for nome, futura in (("sem_chuva", [0.0] * 48), ("chuva_real", P[i + 1: i + 49])):
                # o estado em i tem a chuva até i-1; rodamos a hora i (chuva conhecida) e depois o futuro
                qf = prever(p, est[i], P[max(0, i - lag): i] if lag else [], [P[i]] + futura[:47])
                hf = [nivel_de(q + erro * math.exp(-(h + 1) / tau)) + desvio_h for h, q in enumerate(qf)]
                prev[nome] = max(hf)
            casos.append((i, M.H[i], obs_pico, prev["sem_chuva"], prev["chuva_real"]))
        resultados[tau] = casos

    def metricas(casos, col):
        cruz = [c for c in casos if c[1] < COTA]
        ev = [c for c in cruz if c[2] >= COTA]
        alarmes = [c for c in cruz if c[col] >= COTA]
        acertos = [c for c in ev if c[col] >= COTA]
        sobe = [c for c in casos if c[2] - c[1] >= 50]
        mae = sum(abs(c[col] - c[2]) for c in sobe) / max(1, len(sobe))
        return len(ev), len(acertos) / max(1, len(ev)), 1 - len(acertos) / max(1, len(alarmes)) if alarmes else 0, mae, len(sobe)

    print(f"Fonte de chuva: {fonte}  | NSE validação: {M.nse(Qs, M.fim_calib, M.N):.3f}")
    for tau, casos in resultados.items():
        print(f"\ncorreção de erro tau={tau} h  ({len(casos)} previsões)")
        for nome, col in (("persistência (fica igual)", 1), ("modelo sem chuva futura", 3), ("modelo c/ chuva real", 4)):
            n, pod, far, mae, ns = metricas(casos, col)
            print(f"  {nome:28s} passa da atenção em 48 h: acerta {pod*100:5.1f}% de {n} | alarmes falsos {far*100:5.1f}% | erro médio do pico quando sobe ≥0,5 m: {mae/100:.2f} m (n={ns})")
    json.dump({"tau": resultados}, open(AQUI / f"aval_{fonte}.json", "w"))
