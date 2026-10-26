import math, json
from dados import AQUI, nivel_horario, chuva_horaria
t, bacia, chapeu, local = chuva_horaria()
d = json.load(open(AQUI / "chuva_era5.json"))
pontos = {k: [x or 0 for x in d[k]["p"]] for k in d}
mx = [max(pontos[k][i] for k in ["slp","lagoinha","cunha","cabeceiras","norte"]) for i in range(len(t))]
niv = nivel_horario("58041000"); H = [niv[k][0] if k in niv else None for k in t]
N = len(t); fim = t.index("2022-01-01T00")
acum = [0.0]
for x in bacia: acum.append(acum[-1] + x)
acmx = [0.0]
for x in mx: acmx.append(acmx[-1] + x)
S = lambda a, i, j: a[max(0, min(N, j))] - a[max(0, min(N, i))]   # soma de [i, j)
def corr(x, y):
    n = len(x); mx_, my = sum(x)/n, sum(y)/n
    sxy = sum((a-mx_)*(b-my) for a, b in zip(x, y)); sx = math.sqrt(sum((a-mx_)**2 for a in x)); sy = math.sqrt(sum((b-my)**2 for b in y))
    return sxy / (sx*sy)
linhas = []
for i in range(720, N - 48, 3):
    if H[i] is None: continue
    fut = [H[i+h] for h in range(1, 49) if H[i+h] is not None]
    if len(fut) < 40: continue
    y = max(fut) - H[i]
    linhas.append(dict(i=i, y=y, H0=H[i], p6=S(acum,i-6,i+1), p24=S(acum,i-24,i+1), p72=S(acum,i-72,i+1), api=S(acum,i-720,i-72),
                       f24=S(acum,i+1,i+25), f48=S(acum,i+1,i+49), m48=S(acmx,i+1,i+49)+S(acmx,i-24,i+1)))
y = [l["y"] for l in linhas]
print("n =", len(linhas))
for k in ["p6","p24","p72","api","f24","f48","m48","H0"]:
    print(f"  correlação subida 48h x {k:4s}: {corr([l[k] for l in linhas], y):+.2f}")
comb = [l["p24"] + l["f48"] for l in linhas]
print(f"  correlação subida x (chuva 24h passada + 48h futura): {corr(comb, y):+.2f}")
# subida grande (>=1 m): quanta chuva houve?
grandes = [l for l in linhas if l["y"] >= 100]
peq = [l for l in linhas if l["y"] < 20]
q = lambda v, f: sorted(v)[int(f*(len(v)-1))]
for nome, g in (("subiu >= 1 m", grandes), ("ficou estável (<0,2 m)", peq)):
    v = [l["p24"]+l["f48"] for l in g]
    print(f"  {nome:24s} n={len(g):5d} chuva bacia 24h+48h: mediana {q(v,.5):5.1f} mm | 10% {q(v,.1):5.1f} | 90% {q(v,.9):5.1f}")
json.dump(linhas, open(AQUI / "linhas.json","w"))
