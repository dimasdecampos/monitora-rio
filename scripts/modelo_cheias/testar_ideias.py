"""Testes de nov/2026: cinco ideias para melhorar a previsão de 48 h na Passarela. Nenhuma deu ganho
que valesse; ficam aqui para ninguém repetir sem motivo (resumo no README).

  1. tendência: subida da própria Passarela em 3, 6 e 12 h como variável nova;
  2. tempo:     outro modelo de tempo (ECMWF, GFS, ICON, GEM...) ou a média de 4 no lugar da previsão em uso;
  3. real:      treinar 2024–2026 com a previsão do tempo real, em vez da chuva "perfeita" (ERA5);
  4. teto:      quanto o modelo acertaria se soubesse a chuva futura (ERA5 ou pluviômetro de Barro Vermelho);
  5. cunha:     chuva medida no pluviômetro de Cunha (SP Águas; só tem dado desde dez/2024).

Mesma contagem de passarela.avaliar (aviso = chance >= 30%; treino até 2023, teste fev/2024–out/2026 com a
previsão real). Além dela, cada linha mostra:
  AUC  — o modelo separa bem horas com e sem cheia nas 48 h seguintes? (0,5 = sorteio; 1 = perfeito)
  LL   — log-perda das chances (menor é melhor); usa todos os casos, por isso varia menos que "x de 20 cheias"
  "com <= N falsos" — cheias avisadas quando o limite é subido até ter os mesmos dias falsos da referência
                      (para não confundir modelo melhor com modelo só mais "nervoso").

O ajuste aqui é exato (método de Newton, com numpy) em vez da média de 5 sorteios de passarela.treinar: dá o
mesmo resultado em segundos e sem variar de uma rodada para outra.

Uso: pip install numpy
     python testar_ideias.py [tendencia] [tempo] [real] [teto] [cunha]     (sem argumento: todos)
     ("tempo" e "real" precisam de dados/prev_modelos.json: python baixar_prev_modelos.py)
"""
import sys, json, glob, math, random, statistics as st
from datetime import datetime
import numpy as np
import passarela as M
from dados import AQUI

t, H, N, COTA, GAPS = M.t, M.H, M.N, M.COTA, M.GAPS
TESTE = ("2024-02-01T00", "2026-10-24T00")
DOBRAS = [("2024-02-01T00", "2024-07-01T00"), ("2024-07-01T00", "2025-07-01T00"), ("2025-07-01T00", "2026-10-24T00")]
QUATRO = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_global"]
CUNHA = ["dc6", "dc12"]


# ---------------- dados extras ----------------
def chuva_site(cod):
    """Chuva por hora (mm) do pluviômetro de uma estação, do histórico do site."""
    h = {}
    for f in sorted(glob.glob(f"{M.RAIZ}/public/paraitinga/historico/{cod}/????-??.json")):
        for t_, _, _, ch in json.load(open(f))["dados"]:
            if ch is not None and 0 <= ch <= 120: h[t_[:13]] = h.get(t_[:13], 0) + ch
    return h


CU = M.janelas(chuva_site("sp818"))


def enriquecer(casos):
    for c in casos:
        i = c["i"]
        for h in (3, 6, 12): c[f"h{h}"] = M.dif(H, i, h)
        for h in (6, 24, 72): c[f"cu{h}"] = CU(i - h, i + 1)
    return casos


def montar(ini, fim, passo, chuva, exige):
    return enriquecer(M.montar(ini, fim, passo, chuva, exige))


_prev = None
def prev_modelos():
    global _prev
    if _prev is None:
        d = json.load(open(AQUI / "prev_modelos.json")); _prev = (d, {k[:13]: j for j, k in enumerate(d["t"])})
    return _prev


def f48_modelos(i, modelos, entre="media"):
    """Chuva média na bacia prevista para as 48 h depois da hora i (previsões de 1–2 dias antes)."""
    D, iD = prev_modelos(); dia0 = datetime.strptime(t[i][:10], "%Y-%m-%d"); tot = []
    for m in modelos:
        s = 0.0
        for h in range(1, 49):
            j = iD.get(t[i + h]) if i + h < N else None
            if j is None: return None
            lead = max(1, min(2, (datetime.strptime(t[i + h][:10], "%Y-%m-%d") - dia0).days))
            v = D[m][f"d{lead}"][j]
            if any(x is None for x in v): return None
            s += sum(v) / len(v)
        tot.append(s)
    return max(tot) if entre == "max" else sum(tot) / len(tot)


# ---------------- variáveis novas ----------------
pos = lambda v: max(v or 0, 0) / 100
L = lambda v: math.log1p(v or 0)

def F_T(c, g):      # tendência da própria Passarela
    r3, r6, r12 = pos(c["h3"]), pos(c["h6"]), pos(c["h12"])
    return [r3, r6, r12, r6 / (g + .3)]

def F_CU(c, g):     # pluviômetro de Cunha
    return [L(c["cu6"]), L(c["cu24"]), L(c["cu72"]), L(c["cu24"]) * g]

def fset(versao, *extras):
    return lambda c, G: M.vars_(c, G, versao) + [x for f in extras for x in f(c, G / 100)]


# ---------------- ajuste e contagem ----------------
def matriz(casos, fx):
    X = np.array([fx(c, G) for c in casos for G in GAPS], float)
    y = np.array([1.0 if c["y"] >= G else 0.0 for c in casos for G in GAPS])
    return X, y


def newton(X, y, l2=1e-4, desloc=None, it=60):
    """Regressão logística exata. `desloc` = parte fixa da conta (para ajustar só termos extras)."""
    n, k = X.shape; w = np.zeros(k); desloc = 0 if desloc is None else desloc
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(desloc + X @ w, -30, 30)))
        g = X.T @ (p - y) / n + l2 * w
        d = np.linalg.solve((X * (p * (1 - p))[:, None]).T @ X / n + l2 * np.eye(k), g); w -= d
        if np.abs(d).max() < 1e-8: break
    return w


sig = lambda z: 1 / (1 + math.exp(-max(-30, min(30, z))))

def chances(w, fx, casos):
    """Chance de chegar à atenção em 48 h, por caso (hora i)."""
    return {c["i"]: sig(float(np.dot(w, fx(c, COTA - c["H0"])))) if c["H0"] < COTA else 1.0 for c in casos}


def pontuar(casos, pr):
    por_i = {c["i"]: c for c in casos}; ev = []
    for i in range(1, N):
        if H[i] is not None and H[i - 1] is not None and H[i - 1] < COTA <= H[i] and (not ev or i - ev[-1] > 96): ev.append(i)
    ev = [e for e in ev if any(e - Lh + d in por_i for Lh in (6, 12, 24) for d in (-1, 0, 1))]
    def em(lim):
        res = {}
        for Lh in (3, 6, 12, 24):
            ok = n = 0
            for e in ev:
                c = por_i.get(e - Lh) or por_i.get(e - Lh - 1) or por_i.get(e - Lh + 1)
                if c is None: continue
                n += 1; ok += c["H0"] >= COTA or pr[c["i"]] >= lim
            res[Lh] = (ok, n)
        dias, falsos = set(), set()
        for c in casos:
            if c["H0"] < COTA and pr[c["i"]] >= lim:
                dias.add(t[c["i"]][:10])
                if c["pico"] < COTA: falsos.add(t[c["i"]][:10])
        return res, len(dias), len(falsos)
    ab = [(pr[c["i"]], c["pico"] >= COTA) for c in casos if c["H0"] < COTA]
    s = np.array([a for a, _ in ab]); y = np.array([b for _, b in ab])
    o = s.argsort(); rk = np.empty(len(s)); rk[o] = np.arange(1, len(s) + 1)
    auc = (rk[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum())
    ll = -np.mean(np.where(y, np.log(np.clip(s, 1e-6, 1)), np.log(np.clip(1 - s, 1e-6, 1))))
    return em, auc, ll


def linha(rotulo, casos, pr, falsos_ref=None):
    em, auc, ll = pontuar(casos, pr); res, dias, fa = em(.3)
    txt = (f"  {rotulo:36s} AUC {auc:.3f} LL {ll:.4f} | " + " ".join(f"{Lh} h {ok}/{n}" for Lh, (ok, n) in res.items())
           + f" | dias com aviso {dias}, sem cheia {fa}")
    if falsos_ref is not None:
        for lim in [x / 100 for x in range(5, 96)]:
            r2, _, f2 = em(lim)
            if f2 <= falsos_ref:
                txt += f" || com <= {falsos_ref} falsos (limite {lim:.0%}): " + " ".join(f"{Lh} h {ok}" for Lh, (ok, n) in r2.items()); break
    print(txt, flush=True)
    return fa


# ---------------- 1. tendência da própria Passarela ----------------
def tendencia():
    print("\n[1] Subida da própria Passarela em 3, 6 e 12 h")
    for v, ini, exige in (("P", "2018-01-01T00", M.PLUV), ("BP", "2020-01-01T00", CUNHA + M.PLUV)):
        cv = montar(ini, "2024-01-01T00", 3, "perfeita", exige); tr = cv[::2]; te = montar(*TESTE, 3, "real", exige)
        print(f" versão {v} — {ini[:4]}–2023, um ano de fora por vez (chuva futura da ERA5; {len(cv)} casos):")
        ref = None
        for nome, fx in ((v, fset(v)), (v + " + tendência", fset(v, F_T))):
            pr = {}
            for a in range(int(ini[:4]), 2024):
                dentro = [c for c in cv if t[c["i"]][:4] != str(a)]; fora = [c for c in cv if t[c["i"]][:4] == str(a)]
                if fora: pr.update(chances(newton(*matriz(dentro, fx)), fx, fora))
            fa = linha(nome, cv, pr, ref); ref = fa if ref is None else ref
        print(f" versão {v} — treino até 2023, teste fev/2024–out/2026 com a previsão real ({len(te)} casos):")
        ref = None
        for nome, fx in ((v, fset(v)), (v + " + tendência", fset(v, F_T))):
            fa = linha(nome, te, chances(newton(*matriz(tr, fx)), fx, te), ref); ref = fa if ref is None else ref


# ---------------- 2. outro modelo de tempo ----------------
def tempo():
    D, _ = prev_modelos(); modelos = [m for m in D if m != "t"]
    print("\n[2] Qual modelo de tempo vê melhor a chuva que enche o rio? (previsões de 1–2 dias antes, fev/2024–out/2026)")
    te = [c for c in montar(*TESTE, 3, "real", M.PLUV) if c["H0"] < COTA]
    op = {m: ([m], "media") for m in modelos}
    op.update({"média de 4 (ecmwf, gfs, icon, gem)": (QUATRO, "media"), "maior de 4": (QUATRO, "max"),
               "média de todos": (modelos, "media"), "maior de todos": (modelos, "max")})
    F = {n: {c["i"]: f48_modelos(c["i"], ms, e) for c in te} for n, (ms, e) in op.items()}
    te = [c for c in te if all(F[n][c["i"]] is not None for n in F)]
    y = np.array([c["pico"] >= COTA for c in te])
    med = []   # chuva medida nas 48 h seguintes: média dos pluviômetros de Barro Vermelho e Cunha que tiverem dado
    for c in te:
        v = [x for x in (M.PL(c["i"] + 1, c["i"] + 49), CU(c["i"] + 1, c["i"] + 49)) if x is not None]
        med.append(sum(v) / len(v) if v else None)
    forte = [k for k, v in enumerate(med) if v is not None and v >= 40]
    def auc(f):
        s = np.array(f); o = s.argsort(kind="stable"); rk = np.empty(len(s)); rk[o] = np.arange(1, len(s) + 1)
        for v in set(f):
            m = s == v
            if m.sum() > 1: rk[m] = rk[m].mean()
        return (rk[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum())
    print(f" {len(te)} casos abaixo da atenção, {int(y.sum())} com cheia em 48 h; {len(forte)} com >= 40 mm medidos nos pluviômetros")
    print(f" {'chuva prevista para 48 h':36s} média | AUC (só a chuva) | nos casos de >= 40 mm medidos: mediana prevista")
    def relato(nome, f): print(f" {nome:36s} {st.mean(f):5.1f} |      {auc(f):.3f}       | {st.median(f[k] for k in forte):4.0f} mm", flush=True)
    relato("ERA5 (a chuva 'que aconteceu')", [M.S(c["i"] + 1, c["i"] + 49) for c in te])
    relato("previsão em uso no teste", [M.f48_real(c["i"]) for c in te])
    for n in F: relato(n, [F[n][c["i"]] for c in te])


def casos_4modelos(casos):
    """Os mesmos casos com a chuva prevista trocada pela média de 4 modelos, na escala da ERA5."""
    out = []
    for c in casos:
        f = f48_modelos(c["i"], QUATRO)
        if f is not None: c2 = dict(c); c2["f48"] = f; out.append(c2)
    fator = st.mean(M.S(c["i"] + 1, c["i"] + 49) for c in out) / st.mean(c["f48"] for c in out)
    for c in out: c["f48"] *= fator
    return out, fator


# ---------------- 3. treinar com a previsão real ----------------
def real():
    print("\n[3] Treinar 2024–2026 com a previsão real? (duas estações chuvosas no treino, a terceira no teste)")
    for v, ini, exige in (("P", "2018-01-01T00", M.PLUV), ("BP", "2020-01-01T00", CUNHA + M.PLUV)):
        antigo = montar(ini, "2024-01-01T00", 6, "perfeita", exige)
        re_ = [montar(a, b, 3, "real", exige) for a, b in DOBRAS]; pe = [montar(a, b, 3, "perfeita", exige) for a, b in DOBRAS]
        m4, fator = casos_4modelos([c for d in re_ for c in d]); corte = [M.idx[a] for a, _ in DOBRAS[1:]]
        mm = [[c for c in m4 if sum(c["i"] >= x for x in corte) == k] for k in range(3)]
        def cv(nome, fx, extra, teste, ref=None):
            pr = {}
            for k in range(3):
                tr = antigo + ([c for j in range(3) if j != k for c in extra[j][::2]] if extra else [])
                pr.update(chances(newton(*matriz(tr, fx)), fx, teste[k]))
            return linha(nome, [c for d in teste for c in d], pr, ref)
        print(f" versão {v}:")
        ref = cv("só anos antigos (2023 para trás)", fset(v), None, re_)
        cv("+ 2024–26 com chuva perfeita", fset(v), pe, re_, ref)
        cv("+ 2024–26 com a previsão real", fset(v), re_, re_, ref)
        cv("+ previsão real + tendência", fset(v, F_T), re_, re_, ref)
        print(f"   com a média de 4 modelos de tempo (× {fator:.2f}) no lugar da previsão em uso:")
        ref = cv("só anos antigos", fset(v), None, mm)
        cv("+ 2024–26 com a média de 4 modelos", fset(v), mm, mm, ref)
    # a média de 4 modelos ganha de verdade? diferença de log-perda reamostrando semanas inteiras
    te = montar(*TESTE, 3, "real", M.PLUV); fx = fset("P")
    w = newton(*matriz(montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", M.PLUV), fx))
    m4, _ = casos_4modelos(te); m4 = [c for c in m4 if c["H0"] < COTA]; ids = {c["i"] for c in m4}
    base = [c for c in te if c["i"] in ids and c["H0"] < COTA]; pa, pb = chances(w, fx, base), chances(w, fx, m4)
    ll = lambda p, y: -math.log(max(1e-6, p if y else 1 - p)); sem = {}
    for c in base:
        y = c["pico"] >= COTA; sem.setdefault(c["i"] // 168, []).append((ll(pa[c["i"]], y), ll(pb[c["i"]], y)))
    blocos = list(sem.values()); random.seed(1); difs = []
    for _ in range(2000):
        am = [x for b in random.choices(blocos, k=len(blocos)) for x in b]; difs.append(st.mean(a - b for a, b in am))
    tot = [x for b in blocos for x in b]
    print(f" modelo P, mesmos casos: log-perda {st.mean(a for a, _ in tot):.4f} com a previsão em uso e {st.mean(b for _, b in tot):.4f} "
          f"com a média de 4 modelos;\n ganho a favor da média em {100 * sum(d > 0 for d in difs) / 2000:.0f}% de 2000 reamostragens por semana (95% ou mais = ganho de verdade)")


# ---------------- 4. teto ----------------
def teto():
    print("\n[4] Teto: modelo P treinado até 2023, teste fev/2024–out/2026")
    antigo = montar("2018-01-01T00", "2024-01-01T00", 6, "perfeita", M.PLUV); fx = fset("P")
    re_ = montar(*TESTE, 3, "real", M.PLUV); pe = montar(*TESTE, 3, "perfeita", M.PLUV); w = newton(*matriz(antigo, fx))
    ref = linha("previsão real (como hoje)", re_, chances(w, fx, re_))
    linha("se soubesse a chuva da ERA5", pe, chances(w, fx, pe), ref)
    def troca(casos):   # chuva futura = a medida em Barro Vermelho nas 48 h seguintes
        out = []
        for c in casos:
            v = M.PL(c["i"] + 1, c["i"] + 49)
            if v is not None: c2 = dict(c); c2["f48"] = v; out.append(c2)
        return out
    p2 = troca(pe); linha("se soubesse a chuva em B. Vermelho", p2, chances(newton(*matriz(troca(antigo), fx)), fx, p2), ref)
    # os dias com aviso sem cheia: quão perto o rio chegou
    pr = chances(w, fx, re_); falsos = {}
    for c in re_:
        if c["H0"] < COTA and pr[c["i"]] >= .3 and c["pico"] < COTA:
            d = t[c["i"]][:10]; falsos[d] = max(falsos.get(d, 0), c["pico"])
    print(f" {len(falsos)} dias com aviso sem cheia; pico nas 48 h seguintes (cm; atenção = {COTA:.0f}):", sorted(round(x) for x in falsos.values()))


# ---------------- 5. pluviômetro de Cunha ----------------
def cunha():
    print("\n[5] Pluviômetro de Cunha (só desde dez/2024): termos novos ajustados em duas estações e testados na outra;")
    print("    o resto do modelo fica como treinado até 2023")
    for v, ini, exige in (("P", "2018-01-01T00", M.PLUV), ("BP", "2020-01-01T00", CUNHA + M.PLUV)):
        w0 = newton(*matriz(montar(ini, "2024-01-01T00", 6, "perfeita", exige), fset(v)))
        dob = [[c for c in montar(a, b, 3, "real", exige) if all(c[k] is not None for k in ("cu6", "cu24", "cu72"))] for a, b in DOBRAS]
        todos = [c for d in dob for c in d]; base = lambda c, G: float(np.dot(w0, M.vars_(c, G, v)))
        ref = linha(f"{v} ({len(todos)} casos)", todos, {c["i"]: sig(base(c, COTA - c["H0"])) if c["H0"] < COTA else 1.0 for c in todos})
        pr = {}
        for k in range(3):
            tr = [c for j in range(3) if j != k for c in dob[j][::2]]
            if not tr or not dob[k]: continue
            Xe = np.array([F_CU(c, G / 100) for c in tr for G in GAPS]); y = np.array([1.0 if c["y"] >= G else 0.0 for c in tr for G in GAPS])
            we = newton(Xe, y, l2=1e-3, desloc=np.array([base(c, G) for c in tr for G in GAPS]))
            for c in dob[k]:
                G = COTA - c["H0"]; pr[c["i"]] = sig(base(c, G) + float(np.dot(we, F_CU(c, G / 100)))) if c["H0"] < COTA else 1.0
        linha(f"{v} + chuva medida em Cunha", [c for c in todos if c["i"] in pr], pr, ref)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    partes = {"tendencia": tendencia, "tempo": tempo, "real": real, "teto": teto, "cunha": cunha}
    for nome in (sys.argv[1:] or partes): partes[nome]()
