"""Modelo chuva-vazão simples (horário) para o Paraitinga em São Luiz.

chuva -> umidade do solo (W) -> coeficiente de escoamento -> 2 reservatórios lineares (rápido)
                                                           -> 1 reservatório lento (base)
vazão simulada -> nível pela curva-chave observada (pares vazão x nível da estação)
"""
import json, math, random, sys
from datetime import datetime, timedelta
from dados import AQUI, nivel_horario, chuva_horaria

ESTACAO = sys.argv[1] if len(sys.argv) > 1 else "58041000"
FONTE = sys.argv[2] if len(sys.argv) > 2 else "era5"

t, bacia, chapeu, local = chuva_horaria()
niv = nivel_horario(ESTACAO)
H = [niv[k][0] if k in niv else None for k in t]
Q = [niv[k][1] if k in niv and niv[k][1] is not None and 0 < niv[k][1] < 9000 else None for k in t]

if FONTE == "estacao":
    # pluviômetro da própria estação (soma por hora)
    import glob
    from dados import RAIZ
    ch = {}
    for f in glob.glob(RAIZ + f"/public/paraitinga/historico/{ESTACAO}/????-??.json"):
        for tt, n, v, c in json.load(open(f))["dados"]:
            if c is not None: ch[tt[:13]] = ch.get(tt[:13], 0) + c
    P = [ch.get(k, 0.0) for k in t]
else:
    P = bacia

N = len(t)
fim_calib = t.index("2022-01-01T00")


def simular(p, P=P):
    dw, c0, c1, k1, k2, area, fb, k3, qb0, lag = p
    kw = math.exp(-1 / (24 * dw))
    W = S1 = S2 = 0.0
    S3 = qb0 * k3 / max(area, 1e-6)      # começa com fluxo de base próximo de qb0
    out = [0.0] * len(P)
    lag = int(round(lag))
    for i in range(len(P)):
        pi = P[i - lag] if i >= lag else 0.0
        W = W * kw + pi
        c = c0 + c1 * W / 100.0
        c = 0.0 if c < 0 else (1.0 if c > 1 else c)
        r = c * pi
        S1 += r * (1 - fb); q1 = S1 / k1; S1 -= q1
        S2 += q1; q2 = S2 / k2; S2 -= q2
        S3 += r * fb; q3 = S3 / k3; S3 -= q3
        out[i] = area * (q2 + q3) + qb0
    return out


def nse(sim, a, b):
    obs = [(Q[i], sim[i]) for i in range(a, b) if Q[i] is not None]
    m = sum(o for o, _ in obs) / len(obs)
    return 1 - sum((o - s) ** 2 for o, s in obs) / sum((o - m) ** 2 for o, _ in obs)


LIM = [(1, 60), (0, .6), (0, 1.5), (1, 60), (1, 80), (10, 600), (0, .8), (100, 4000), (0, 20), (0, 12)]
def calibrar(iters=500, semente=1):
    random.seed(semente)
    p = [10, .1, .3, 8, 12, 150, .3, 800, 5, 3]
    best = nse(simular(p), 1000, fim_calib)
    passo = [ (hi - lo) * .25 for lo, hi in LIM ]
    for it in range(iters):
        j = it % len(p)
        for sinal in (1, -1):
            q = p[:]; q[j] = min(LIM[j][1], max(LIM[j][0], q[j] + sinal * passo[j] * (0.5 + random.random())))
            v = nse(simular(q), 1000, fim_calib)
            if v > best: best, p = v, q; break
        else:
            passo[j] *= .7
    return p, best


if __name__ == "__main__":
    p, b = calibrar(int(sys.argv[3]) if len(sys.argv) > 3 else 400)
    sim = simular(p)
    print(f"{ESTACAO} chuva={FONTE}: NSE calibração 2015–2021 = {b:.3f} | validação 2022–2026 = {nse(sim, fim_calib, N):.3f}")
    print("parâmetros:", [round(x, 3) for x in p])
    json.dump({"p": p, "estacao": ESTACAO, "fonte": FONTE}, open(AQUI / f"param_{ESTACAO}_{FONTE}.json", "w"))
