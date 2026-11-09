"""Testa se vento do mar contra a Serra e energia de tempestade (CAPE) ajudam a prever cheias.

Parte 1 (diagnóstico): para cada cheia de 2024–2026 na Passarela, o que a previsão feita 1–2 dias antes
dizia de vento do mar e CAPE nas 48 h seguintes, 12 e 24 h antes da cheia, comparado com as outras horas
da estação chuvosa (out–mar). Mostra também a chance do modelo atual (P, treinado até 2023).

Vento do mar: velocidade × cos(direção − 150°) no litoral (Ubatuba). Positivo quando sopra de SE,
de frente para a Serra do Mar.

Parte 2 (--modelo): o modelo de 48 h com e sem as variáveis novas, treinado até 2023 e testado em
fev/2024–out/2026 com a previsão do tempo real (chuva, vento e CAPE previstos 1–2 dias antes).
V = vento do mar (treino com ERA5); C = V + CAPE (termos extras ajustados em 2022–2023 com as previsões
históricas, demais pesos fixos). Mesma contagem de passarela.avaliar.

Uso: python testar_atmosfera.py                                   (diagnóstico, Passarela)
     python testar_atmosfera.py --modelo --bacia paraitinga|paraibuna
"""
import json, math, random
from pathlib import Path
from datetime import datetime
import passarela as M
from dados import AQUI

A = json.load(open(AQUI / "atm_prev.json"))
iA = {k[:13]: j for j, k in enumerate(A["litoral"]["t"])}


def mar(ws, wd):
    return None if ws is None or wd is None else ws * math.cos(math.radians(wd - 150))


def previsto(i, horas=48):
    """Previsão (feita 1–2 dias antes) para as próximas `horas` a partir da hora i: vento do mar médio
    e máximo no litoral, horas com vento do mar > 10 km/h e CAPE máximo (litoral e serra)."""
    dia0 = datetime.strptime(M.t[i][:10], "%Y-%m-%d"); vm, cp = [], []
    for h in range(1, horas + 1):
        if i + h >= M.N: return None
        j = iA.get(M.t[i + h])
        if j is None: return None
        lead = max(1, min(2, (datetime.strptime(M.t[i + h][:10], "%Y-%m-%d") - dia0).days))
        L, S = A["litoral"], A["serra"]
        v = mar(L[f"wind_speed_10m_previous_day{lead}"][j], L[f"wind_direction_10m_previous_day{lead}"][j])
        c = [L[f"cape_previous_day{lead}"][j], S[f"cape_previous_day{lead}"][j]]
        if v is None or None in c: return None
        vm.append(v); cp.append(max(c))
    return dict(mar_med=sum(vm) / len(vm), mar_max=max(vm), mar_h=sum(x > 10 for x in vm), cape=max(cp))


def diagnostico():
    w = json.load(open(AQUI / "pesos_P_ate2023.json")) if (AQUI / "pesos_P_ate2023.json").exists() else None
    if w is None:
        print("treinando o modelo P até 2023...", flush=True)
        w = M.treinar_media(M.montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", M.PLUV), "P")
        json.dump(w, open(AQUI / "pesos_P_ate2023.json", "w"))
    i0, i1 = M.idx["2024-02-01T00"], M.idx["2026-10-24T00"]
    eventos = []
    for e in range(i0, i1):
        if M.H[e] is not None and M.H[e - 1] is not None and M.H[e - 1] < M.COTA <= M.H[e] and (not eventos or e - eventos[-1] > 96):
            eventos.append(e)
    # referência: todas as horas da estação chuvosa (out–mar) abaixo da atenção
    ref = {k: [] for k in ("mar_med", "mar_max", "mar_h", "cape")}
    for i in range(i0, i1, 3):
        if int(M.t[i][5:7]) not in (10, 11, 12, 1, 2, 3) or M.H[i] is None or M.H[i] >= M.COTA: continue
        x = previsto(i)
        if x: [ref[k].append(x[k]) for k in ref]
    for k in ref: ref[k].sort()
    pct = lambda k, v: round(100 * sum(r <= v for r in ref[k]) / len(ref[k]))

    def chance(i):
        f = M.f48_real(i); c = M.caso(i, f) if f is not None else None
        if c is None or any(c[k] is None for k in M.PLUV): return None
        return M.prob(w, c, M.COTA - c["H0"], "P")

    print(f"{len(eventos)} cheias na Passarela; valores = percentil entre {len(ref['cape'])} horas de out–mar sem cheia "
          "(50 = típico, 90 = só 10% das horas têm mais)\n")
    print("cheia            | 24 h antes: chance  mar_méd  mar_máx  h_mar  CAPE | 12 h antes: chance  mar_méd  mar_máx  h_mar  CAPE")
    soma = {L: {k: [] for k in ref} for L in (24, 12)}
    for e in eventos:
        linha = f"{M.t[e]}  |"
        for L in (24, 12):
            x = previsto(e - L); p = chance(e - L)
            if x is None:
                linha += "      (sem previsão arquivada)                   |"; continue
            for k in ref: soma[L][k].append(pct(k, x[k]))
            linha += (f"      {'  -- ' if p is None else f'{p*100:4.0f}%'}  " +
                      "  ".join(f"{pct(k, x[k]):6d}" for k in ref) + " |")
        print(linha)
    print("\nmediana dos percentis nas cheias (50 = nada de diferente; 80+ = sinal forte):")
    for L in (24, 12):
        print(f"  {L} h antes: " + ", ".join(f"{k} {sorted(v)[len(v)//2]}" for k, v in soma[L].items() if v))


# ---------------- parte 2: teste honesto ----------------
E5 = json.load(open(AQUI / "atm_era5.json")); iE = {k[:13]: j for j, k in enumerate(E5["litoral"]["t"])}
HI = json.load(open(AQUI / "atm_hist.json")); iH = {k[:13]: j for j, k in enumerate(HI["litoral"]["t"])}


def atm(t, i, fonte):
    """Vento do mar médio (km/h) e CAPE máximo nas 48 h depois da hora i. fonte: era5 (o que aconteceu;
    sem CAPE), hist (previsões históricas 2022+) ou prev (previsão feita 1–2 dias antes)."""
    vm, cp = [], []
    dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d")
    for h in range(1, 49):
        if i + h >= len(t): return None
        k = t[i + h]
        if fonte == "prev":
            j = iA.get(k)
            if j is None: return None
            lead = max(1, min(2, (datetime.strptime(k[:10], "%Y-%m-%d") - dia0).days))
            L, S = A["litoral"], A["serra"]
            v = mar(L[f"wind_speed_10m_previous_day{lead}"][j], L[f"wind_direction_10m_previous_day{lead}"][j])
            c = max(L[f"cape_previous_day{lead}"][j] or 0, S[f"cape_previous_day{lead}"][j] or 0)
        else:
            D, ix = (E5, iE) if fonte == "era5" else (HI, iH)
            j = ix.get(k)
            if j is None: return None
            v = mar(D["litoral"]["wind_speed_10m"][j], D["litoral"]["wind_direction_10m"][j])
            c = max(D["litoral"]["cape"][j] or 0, D["serra"]["cape"][j] or 0) if "cape" in D["litoral"] else 0
        if v is None: return None
        vm.append(v); cp.append(c)
    return sum(vm) / len(vm), max(cp)


def extras(c, g, versao):
    m = max(c["mar"], 0) / 10; x = [m, m * g, m * math.log1p(c["f48"])]
    if "C" in versao:
        k = math.log1p(c["cape"] / 100); x += [k, k * m]
    return x


def treinar_x(dados, n, w0=None, livres=None, epocas=50, lr=.05, l2=1e-4, sementes=(1, 2, 3)):
    """Regressão logística (mesmo Adam de passarela.treinar), média de 3 sorteios; `livres` = pesos que mudam."""
    ws = []
    for sem in sementes:
        random.seed(sem); d = dados[:]
        w = list(w0) if w0 else [0.0] * n; m = [0.0] * n; v = [0.0] * n; passo = 0
        J = livres if livres is not None else range(n)
        for _ in range(epocas):
            random.shuffle(d)
            for k in range(0, len(d), 256):
                lote = d[k:k + 256]; grad = [0.0] * n
                for x, y in lote:
                    z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-max(-30, min(30, z))))
                    for j in J: grad[j] += (p - y) * x[j]
                passo += 1
                for j in J:
                    gj = grad[j] / len(lote) + l2 * w[j]
                    m[j] = .9 * m[j] + .1 * gj; v[j] = .999 * v[j] + .001 * gj * gj
                    w[j] -= lr * (m[j] / (1 - .9 ** passo)) / (math.sqrt(v[j] / (1 - .999 ** passo)) + 1e-8)
        ws.append(w)
    return [sum(w[j] for w in ws) / len(ws) for j in range(n)]


def teste_modelo(bacia):
    if bacia == "paraitinga":
        t, H, COTA, N, GAPS = M.t, M.H, M.COTA, M.N, M.GAPS
        base = {"P": ("2018-01-01T00", M.PLUV), "BP": ("2020-01-01T00", ["dc6", "dc12"] + M.PLUV)}
        montar = lambda ini, fim, passo, chuva, v: M.montar(ini, fim, passo, chuva, base[v][1])
        vb = lambda c, G, v: M.vars_(c, G, v)
    else:
        import sys
        arq = Path(__file__).parent / "treinar_bacia.py"
        src = arq.read_text(encoding="utf-8")
        src = src[:src.index("\ninicio = next(")]   # só a parte que carrega os dados (não treina nem grava nada)
        ns = {"__file__": str(arq), "__name__": "treinar_bacia_dados"}
        argv = sys.argv; sys.argv = ["treinar_bacia.py", "--bacia", bacia]
        exec(compile(src, str(arq), "exec"), ns); sys.argv = argv
        t, H, COTA, N, GAPS = ns["t"], ns["H"], ns["COTA"], ns["N"], ns["GAPS"]
        ini0 = max(next(t[i] for i in range(720, N) if H[i] is not None), "2015-01-01T00")
        ini_b = next(t[i] for i in range(720, N) if ns["HR"][i] is not None and H[i] is not None)
        base = {"A": (ini0, False), "B": (ini_b, True)}
        montar = lambda ini, fim, passo, chuva, v: ns["montar"](ini, fim, passo, chuva, base[v][1])
        vb = lambda c, G, v: ns["vars_"](c, G, v)

    def com_atm(casos, fonte):
        out = []
        for c in casos:
            a = atm(t, c["i"], fonte)
            if a: c["mar"], c["cape"] = a; out.append(c)
        return out

    eventos = []
    for e in range(1, N):
        if H[e] is not None and H[e - 1] is not None and H[e - 1] < COTA <= H[e] and (not eventos or e - eventos[-1] > 96):
            eventos.append(e)

    def avaliar(casos, pf, rotulo):
        por_i = {c["i"]: c for c in casos}
        ev = [e for e in eventos if any(e - L + d in por_i for L in (6, 12, 24) for d in (-1, 0, 1))]
        res = {}
        for L in (3, 6, 12, 24):
            ok = n = 0
            for e in ev:
                c = por_i.get(e - L) or por_i.get(e - L - 1) or por_i.get(e - L + 1)
                if c is None: continue
                n += 1; ok += c["H0"] >= COTA or pf(c, COTA - c["H0"]) >= .3
            res[L] = (ok, n)
        dias, falsos = set(), set()
        for c in casos:
            if c["H0"] < COTA and pf(c, COTA - c["H0"]) >= .3:
                dias.add(t[c["i"]][:10])
                if c["pico"] < COTA: falsos.add(t[c["i"]][:10])
        print(f"  {rotulo:34s} " + " | ".join(f"{L:2d} h: {ok}/{n}" for L, (ok, n) in res.items())
              + f" | dias com aviso {len(dias)}, sem cheia {len(falsos)}", flush=True)

    sig = lambda z: 1 / (1 + math.exp(-max(-30, min(30, z))))
    for v, (ini, _) in base.items():
        print(f"\n{bacia}, versão {v} (treino desde {ini[:7]}):", flush=True)
        tr = com_atm(montar(ini, "2024-01-01T00", 6, "perfeita", v), "era5")
        te = com_atm(montar("2024-02-01T00", "2026-10-24T00", 3, "real", v), "prev")
        print(f"    {len(tr)} casos de treino, {len(te)} de teste", flush=True)
        dados0 = [(vb(c, G, v), 1.0 if c["y"] >= G else 0.0) for c in tr for G in GAPS]
        w0 = treinar_x(dados0, len(dados0[0][0]))
        avaliar(te, lambda c, G: sig(sum(a * b for a, b in zip(w0, vb(c, G, v)))), f"{v} (atual)")
        fV = lambda c, G: vb(c, G, v) + extras(c, G / 100, "V")
        dadosV = [(fV(c, G), 1.0 if c["y"] >= G else 0.0) for c in tr for G in GAPS]
        wV = treinar_x(dadosV, len(dadosV[0][0]))
        avaliar(te, lambda c, G: sig(sum(a * b for a, b in zip(wV, fV(c, G)))), f"{v}+V (vento do mar)")
        # C: termos do CAPE ajustados em 2022–2023 com as previsões históricas; o resto fica fixo em wV
        trC = com_atm(montar("2022-01-01T00", "2024-01-01T00", 3, "perfeita", v), "hist")
        fC = lambda c, G: vb(c, G, v) + extras(c, G / 100, "VC")
        dadosC = [(fC(c, G), 1.0 if c["y"] >= G else 0.0) for c in trC for G in GAPS]
        n = len(dadosC[0][0]); wC = treinar_x(dadosC, n, w0=wV + [0.0, 0.0], livres=[0, n - 2, n - 1])
        avaliar(te, lambda c, G: sig(sum(a * b for a, b in zip(wC, fC(c, G)))), f"{v}+V+C (vento do mar e CAPE)")
        print(f"    pesos novos V: {[round(x, 2) for x in wV[-3:]]}  C: {[round(x, 2) for x in wC[-2:]]}", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--modelo", action="store_true"); ap.add_argument("--bacia", default="paraitinga")
    a = ap.parse_args()
    teste_modelo(a.bacia) if a.modelo else diagnostico()
