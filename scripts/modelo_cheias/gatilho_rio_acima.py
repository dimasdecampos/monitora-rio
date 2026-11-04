"""Testa o gatilho rio acima: avisar quando a régua de Barro Vermelho (Lagoinha) sobe muito em 12 h,
além do aviso do modelo de probabilidade (versão P, chance ≥ 30%).

A água leva ~9 h de Barro Vermelho até a Passarela. Nas cheias que o modelo perdeu em 2024–2026, essa
régua já tinha subido 80–137 cm em 12 h. O nível dela não entra no modelo porque a SP Águas quase não
tem histórico antes de 2024 (só alguns meses de janeiro); por isso o gatilho é uma regra simples,
testada só em out/2024–out/2026 (quando a régua transmite).

Os parâmetros vêm de public/paraitinga/config.json → previsao.gatilho (estacao, sobe_cm, horas).
Conta uma cheia como avisada com L horas se o aviso estava ligado em alguma hora entre L+6 e L horas
antes de a Passarela passar da atenção. Um dia com aviso "sem cheia" é um dia em que o aviso ligou e a
Passarela não passou da atenção nas 36 h seguintes.

Uso: python gatilho_rio_acima.py   (depois de baixar_chuva.py, baixar_prev7.py e baixar_pluviometro.py)
"""
import json
import passarela as M

cfg = json.load(open(f"{M.RAIZ}/public/paraitinga/config.json", encoding="utf-8"))["previsao"]["gatilho"]
REGUA = M.serie_sp(cfg["estacao"]); R = [REGUA.get(k) for k in M.t]
i0, i1 = M.idx["2024-10-01T00"], M.idx["2026-10-24T00"]

print("treinando o modelo P até 2023...", flush=True)
w = M.treinar_media(M.montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", M.PLUV), "P")

eventos = []
for e in range(i0, i1):
    if M.H[e] is not None and M.H[e - 1] is not None and M.H[e - 1] < M.COTA <= M.H[e] and (not eventos or e - eventos[-1] > 96):
        eventos.append(e)

p = {}   # chance do modelo P a cada hora, com a previsão do tempo real da época
for i in range(i0 - 30, i1):
    f = M.f48_real(i)
    if f is None: continue
    c = M.caso(i, f)
    if c is None or any(c[k] is None for k in M.PLUV): continue
    p[i] = M.prob(w, c, M.COTA - c["H0"], "P")


def sobe(i, h):
    return None if R[i] is None or R[i - h] is None else R[i] - R[i - h]


def teste(nome, alarme):
    liga = {i for i in range(i0, i1) if M.H[i] is not None and M.H[i] < M.COTA and alarme(i)}
    res = {L: sum(any(i in liga for i in range(e - L - 6, e - L + 1)) for e in eventos) for L in (3, 6, 12)}
    dias = {M.t[i][:10] for i in liga}
    falsos = {M.t[i][:10] for i in liga if max((x for x in M.H[i:i + 36] if x is not None), default=0) < M.COTA}
    print(f"  {nome:48s} " + " | ".join(f"{L:2d} h antes: {res[L]}/{len(eventos)}" for L in res)
          + f" | dias com aviso {len(dias)}, sem cheia {len(falsos)}")


G, Hs = cfg["sobe_cm"], cfg["horas"]
print(f"\n{len(eventos)} vezes em que a Passarela passou da atenção (out/2024 a out/2026):")
teste("modelo P (chance >= 30%)", lambda i: p.get(i, 0) >= .3)
teste(f"gatilho sozinho (>= {G} cm em {Hs} h)", lambda i: (sobe(i, Hs) or 0) >= G)
teste(f"modelo P ou gatilho", lambda i: p.get(i, 0) >= .3 or (sobe(i, Hs) or 0) >= G)
print("\nsensibilidade do limite:")
for g in (40, 50, 60, 70, 80):
    teste(f"modelo P ou >= {g} cm em {Hs} h", lambda i, g=g: p.get(i, 0) >= .3 or (sobe(i, Hs) or 0) >= g)
