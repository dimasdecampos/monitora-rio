"""Linha de previsão das próximas 48 h na Passarela a partir das réguas rio acima.

Por quê: na cheia de 26–27/11/2026 a linha antiga (só chuva + subida de Cunha) mostrou o rio descendo o tempo
todo enquanto ele subia mais de 1 m: Cunha já baixava, mas a onda do Jacuí e de Lagoinha ainda vinha.
A chuva medida foi moderada (17–69 mm nos pluviômetros), então só as réguas viram a cheia chegando.

Para cada prazo h (1 a 24 h, de hora em hora, e 30 a 48 h), uma regressão linear estima H(t+h) − H(t) na Passarela a partir de:
  - nível e subida da própria Passarela (1, 3 e 6 h);
  - nível e subida da régua de Barro Vermelho, em Lagoinha (3, 6 e 12 h);
  - subida da régua de Cunha (6 e 12 h);
  - chuva na bacia (previsão do tempo: 24 h passadas e o que vem até t+h).
A faixa vem dos erros do próprio modelo no treino (quantis por faixa de previsão, como na linha antiga).
Momentos com o rio alto ou mexendo pesam 10× no ajuste (são poucos e são os que importam).

Teste: treino 2024–2025, teste 2026 (inclui as cheias de janeiro e de novembro), comparado com a linha antiga.
Gravação (--gravar): treina com tudo e grava em public/paraitinga/modelo_cheias.json → passarela.rio_acima.

Uso: python rio_acima.py [--gravar]   (depois de baixar_prev7.py; usa o histórico do site)
"""
import json, math, sys, glob
from datetime import datetime, timedelta
from dados import AQUI, RAIZ, c as coletar

PRAZOS = list(range(1, 25)) + [30, 36, 42, 48]   # até 48 h também erra menos que a linha por chuva (teste 2026)
QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
REGUAS = {"P": "sp664", "B": "sp662", "C": "sp818"}
MODELO = f"{RAIZ}/public/paraitinga/modelo_cheias.json"
site = json.load(open(MODELO, encoding="utf-8"))
FATOR = site["fator_previsao"]


def serie(cod):
    linhas = []
    for f in sorted(glob.glob(f"{RAIZ}/public/paraitinga/historico/{cod}/????-??.json")):
        linhas += json.load(open(f, encoding="utf-8"))["dados"]
    linhas = coletar.sem_picos_falsos(sorted(linhas))
    return {t[:13]: n for t, n, _, _ in linhas if n is not None}


S = {k: serie(c) for k, c in REGUAS.items()}
pv = json.load(open(AQUI / "chuva_prevista7.json"))
chuva = {k[:13]: v for k, v in zip(pv["t"], pv["d1"]) if v is not None}   # previsão feita na véspera ≈ o que o painel recebe
fim = max(S["P"])
t0 = datetime(2024, 1, 1)
T = [(t0 + timedelta(hours=k)).strftime("%Y-%m-%dT%H") for k in range(int((datetime.strptime(fim, "%Y-%m-%dT%H") - t0).total_seconds() // 3600) + 1)]
N = len(T)
g = lambda s, i: S[s].get(T[i]) if 0 <= i < N else None
acum, ok = [0.0], [0]
for k in T: acum.append(acum[-1] + chuva.get(k, 0)); ok.append(ok[-1] + (k in chuva))
def soma(a, b):
    a, b = max(0, a), min(N, b)
    return None if b <= a or ok[b] - ok[a] < b - a else acum[b] - acum[a]


def variaveis(p, b, c, r24, rfut):
    """p, b, c: nível agora e h horas antes {0,1,3,6,12} (cm); r24: chuva das últimas 24 h; rfut: chuva prevista até t+h (mm).
    Mesma conta em modelos/painel.html (linhaRioAcima) e em scripts/alertas.py (trajetoria)."""
    n = p[0] / 100
    db3, db6 = (b[0] - b[3]) / 100, (b[0] - b[6]) / 100
    rf = math.log1p(rfut)
    return [1.0, n, n * n, (p[0] - p[1]) / 100, (p[0] - p[3]) / 100, (p[0] - p[6]) / 100,
            b[0] / 100, db3, db6, (b[0] - b[12]) / 100, max(db3, 0) * n, max(db6, 0) * n,
            (c[0] - c[6]) / 100, (c[0] - c[12]) / 100, math.log1p(r24), rf, rf * n]


def entrada(i, h):
    p = {d: g("P", i - d) for d in (0, 1, 3, 6)}
    b = {d: g("B", i - d) for d in (0, 3, 6, 12)}
    c = {d: g("C", i - d) for d in (0, 6, 12)}
    if None in (*p.values(), *b.values(), *c.values()): return None
    r24, rfut = soma(i - 23, i + 1), soma(i + 1, i + h + 1)
    if r24 is None or rfut is None: return None
    return variaveis(p, b, c, r24, rfut * FATOR)


def agitado(i):
    p0, p3 = g("P", i), g("P", i - 3)
    return p0 > 150 or abs(p0 - p3) > 10


def resolver(A, y, w, ridge=1e-4):
    """Mínimos quadrados ponderados com regularização leve (eliminação de Gauss)."""
    k = len(A[0]); M = [[0.0] * (k + 1) for _ in range(k)]
    for x, v, p in zip(A, y, w):
        for a in range(k):
            xa = x[a] * p; Ma = M[a]
            for j in range(a, k): Ma[j] += xa * x[j]
            Ma[k] += xa * v
    for a in range(k):
        for j in range(a): M[a][j] = M[j][a]
    tr = sum(w)
    for a in range(1, k): M[a][a] += ridge * tr
    for col in range(k):
        piv = max(range(col, k), key=lambda r: abs(M[r][col])); M[col], M[piv] = M[piv], M[col]
        for r in range(k):
            if r != col and M[r][col]:
                f = M[r][col] / M[col][col]
                for j in range(col, k + 1): M[r][j] -= f * M[col][j]
    return [M[a][k] / M[a][a] for a in range(k)]


def amostras(ini, fim_, h):
    for i in range(N - h):
        if not (ini <= T[i] < fim_): continue
        y = g("P", i + h)
        if y is None: continue
        x = entrada(i, h)
        if x is None: continue
        yield i, x, y - g("P", i)


def quantil(v, q): s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))]


def ajustar(ini, fim_, h):
    tr = list(amostras(ini, fim_, h))
    w = resolver([x for _, x, _ in tr], [y for _, _, y in tr], [10 if agitado(i) else 1 for i, _, _ in tr])
    pred = lambda x: sum(a * b for a, b in zip(w, x))
    # faixa: quantis dos erros por faixa de previsão, separados para rio calmo e agitado
    # (os momentos calmos são 90% das horas e deixariam a faixa estreita demais nas cheias)
    faixas = {}
    for nome, sel in (("calmo", [s for s in tr if not agitado(s[0])]), ("agitado", [s for s in tr if agitado(s[0])])):
        pares = sorted((pred(x), y - pred(x)) for _, x, y in sel); nb = 6 if nome == "calmo" else 4; fx = []
        for k in range(nb):
            bloco = pares[k * len(pares) // nb:(k + 1) * len(pares) // nb]
            fx.append({"ate": round(bloco[-1][0], 2) if k < nb - 1 else 1e9, "q": [round(quantil([r for _, r in bloco], q), 1) for q in QS]})
        faixas[nome] = fx
    return w, faixas, pred, len(tr)


def quantis(fx, i, p):
    """Quantis do erro para a previsão p (cm) feita na hora i."""
    return next(f for f in fx["agitado" if agitado(i) else "calmo"] if p <= f["ate"])["q"]


# ---- linha antiga (a que está no site), com a mesma chuva, para comparar ----
tj = site["passarela"]["trajetoria"]
def antiga(i, h):
    pz = next((z for z in tj["prazos"] if z["h"] == h), None)
    if pz is None: return None
    a, b, s = soma(i - 24, i + 1), soma(i - 72, i + 1), soma(i - 720, i - 72)
    fut, fim24 = soma(i + 1, i + h + 1), soma(i + h - 23, i + h + 1)
    if None in (a, b, s, fut, fim24): return None
    p0, c0, c6 = g("P", i), g("C", i), g("C", i - 6)
    dc6 = (c0 - c6) if c0 is not None and c6 is not None else 0
    n, xa, xs = p0 / 100, math.log1p(a), s / 100
    ra, rf = math.log1p(fut * FATOR), math.log1p(fim24 * FATOR)
    v = [1, n, n * n, xa, math.log1p(b), xs, ra, rf, ra * xs, rf * xs, ra * n, xa * (24 / (h + 24)), max(dc6, 0) / 100 * (24 / (h + 24))]
    p = sum(w * x for w, x in zip(pz["pesos"], v))
    q = next(f for f in pz["faixas"] if p <= f["ate"])["q"]
    return p0 + p + q[3]


if __name__ == "__main__":
    print(f"dados até {fim}; treino 2024–2025, teste 2026\n")
    TESTE = ("2026-01-01T00", "9999")
    modelos = {}
    print(f"{'prazo':>5} | {'só rio alto ou mexendo (P>1,5 m ou ±10 cm/3 h)':^52} | {'todas as horas':^30}")
    print(f"{'':>5} | {'novo':>8} {'antiga':>8} {'fica igual':>10} {'faixa':>8} {'n':>6} | {'novo':>8} {'antiga':>8} {'fica igual':>10}")
    for h in PRAZOS:
        w, fx, pred, ntr = ajustar("2024-01-01T00", "2026-01-01T00", h)
        modelos[h] = (w, fx)
        te = list(amostras(*TESTE, h))
        def linha(sel):
            e_n = [abs(pred(x) + quantis(fx, i, pred(x))[3] - y) for i, x, y in sel]
            e_i = [abs(y) for _, _, y in sel]
            e_a = [abs(antiga(i, h) - g("P", i + h)) for i, _, _ in sel if antiga(i, h) is not None]
            cob = sum(pred(x) + quantis(fx, i, pred(x))[1] <= y <= pred(x) + quantis(fx, i, pred(x))[5] for i, x, y in sel) / max(1, len(sel))
            m = lambda v: f"{sum(v) / len(v):6.1f}cm" if v else "     -  "
            return m(e_n), m(e_a), m(e_i), f"{cob * 100:5.0f}%", len(sel)
        ag = linha([s for s in te if agitado(s[0])]); tudo = linha(te)
        if h in (1, 3, 6, 9, 12, 18, 24):
            print(f"{h:>4}h | {ag[0]:>8} {ag[1]:>8} {ag[2]:>10} {ag[3]:>8} {ag[4]:>6} | {tudo[0]:>8} {tudo[1]:>8} {tudo[2]:>10}")

    def mostrar(ini, fim_, passo=3):
        hs = [3, 6, 12, 18, 24]
        print(f"{'hora':>12} {'nível':>6} | " + " | ".join(f"+{h}h novo/antiga/real" for h in hs))
        for i in range(N):
            if not (ini <= T[i] <= fim_) or int(T[i][11:13]) % passo: continue
            if g("P", i) is None: continue
            cel = []
            for h in hs:
                x = entrada(i, h); w, fx = modelos[h]
                pp = sum(a * b for a, b in zip(w, x)) if x else None
                nv = g("P", i) + pp + quantis(fx, i, pp)[3] if x else None
                an, re = antiga(i, h), g("P", i + h)
                f_ = lambda v: f"{v:4.0f}" if v is not None else "   -"
                cel.append(f"{f_(nv)}/{f_(an)}/{f_(re)}")
            print(f"{T[i][5:13]:>12} {g('P', i):6.0f} | " + " | ".join(f"{c:^19}" for c in cel))

    print("\nCheia de 26–27/nov/2026 (previsão feita na hora indicada):"); mostrar("2026-11-25T21", "2026-11-27T12")
    print("\nCheia de jan/2026:"); mostrar("2026-01-25T12", "2026-01-28T12", 6)

    if "--gravar" in sys.argv:
        prazos = []
        for h in PRAZOS:
            w, fx, _, ntr = ajustar("2024-01-01T00", "9999", h)
            prazos.append({"h": h, "pesos": [round(v, 6) for v in w], "faixas": fx})
        site["passarela"]["rio_acima"] = {
            "versao": datetime.now().date().isoformat(), "estacao": REGUAS["B"], "cunha": REGUAS["C"],
            "descricao": "Linha de 1 a 48 h na Passarela pelas réguas rio acima (Barro Vermelho e Cunha) e a subida da própria régua. Sem essas réguas, vale a linha por chuva.",
            "treino": f"2024-01 a {fim[:10]}", "quantis": QS, "prazos": prazos}
        json.dump(site, open(MODELO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\ngravado em", MODELO)
