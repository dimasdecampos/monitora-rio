"""Qual previsão de chuva acerta mais na bacia do Paraitinga? Compara a chuva prevista 1, 2 e 3 dias antes
por 8 modelos de tempo (Open-Meteo, previsões arquivadas) com a chuva medida nos pluviômetros da SP Águas,
no mesmo ponto de cada pluviômetro, dia a dia, de 2024 até ontem.

Baixa as previsões em dados/prev_modelos_pluv.json (--baixar força baixar de novo, para incluir os dias novos)
e grava o resumo em dados/avaliacao_chuva.json e public/admin/chuva.json (página /admin do site; o
GitHub Actions refaz todo dia).

Uso: python avaliar_chuva_prevista.py [--baixar]
"""
import argparse, json, math, time, urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
HIST = AQUI.parent.parent / "public/paraitinga/historico"
# pluviômetros (código no site, nome, lat, lon)
PLUV = [("sp664", "São Luiz (Passarela)", -23.2227, -45.3121), ("sp662", "Lagoinha (Barro Vermelho)", -23.1391, -45.167),
        ("sp818", "Cunha", -22.9951, -45.0439), ("sp489", "Ribeirão do Chapéu", -23.249, -45.2853)]
MODELOS = {"best_match": "Padrão Open-Meteo (usado no site)", "ecmwf_ifs025": "ECMWF (europeu)", "gfs_seamless": "GFS (EUA)",
           "icon_seamless": "ICON (alemão)", "gem_global": "GEM (canadense)", "meteofrance_seamless": "Météo-France",
           "jma_seamless": "JMA (japonês)", "cma_grapes_global": "CMA (chinês)"}
DIAS_ANTES = (1, 2, 3)
INICIO = "2024-01-01"

a = argparse.ArgumentParser(); a.add_argument("--baixar", action="store_true"); ARGS = a.parse_args()


def baixar(destino):
    lat = ",".join(str(p[2]) for p in PLUV); lon = ",".join(str(p[3]) for p in PLUV)
    cols = [f"precipitation_previous_day{k}" for k in DIAS_ANTES]
    saida = {"t": [], **{m: {f"d{k}": [] for k in DIAS_ANTES} for m in MODELOS}}
    hoje = date.today()
    blocos, ini = [], date.fromisoformat(INICIO)
    while ini <= hoje:
        fim = min(date(ini.year, 6, 30) if ini.month <= 6 else date(ini.year, 12, 31), hoje)   # meio ano por vez
        blocos.append((ini, fim)); ini = fim + timedelta(days=1)
    for ini, fim in blocos:
        url = (f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&hourly={','.join(cols)}&start_date={ini}&end_date={fim}"
               f"&timezone=America%2FSao_Paulo&models={','.join(MODELOS)}")
        for k in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "monitor-rios"}), timeout=600)); break
            except Exception as e:
                print("erro", e, flush=True); time.sleep(30)
        else:
            raise RuntimeError(f"não foi possível baixar {ini} a {fim}")
        tt = d[0]["hourly"]["time"]
        for m in MODELOS:
            for k in DIAS_ANTES:
                col = f"precipitation_previous_day{k}_{m}"
                saida[m][f"d{k}"] += [[r["hourly"].get(col, [None] * len(tt))[i] for r in d] for i in range(len(tt))]
        saida["t"] += tt
        print(ini, fim, "ok", flush=True)
    destino.write_text(json.dumps(saida))


DADOS.mkdir(exist_ok=True)
arq = DADOS / "prev_modelos_pluv.json"
if ARGS.baixar or not arq.exists(): baixar(arq)
prev = json.loads(arq.read_text())

# chuva medida por dia (hora de Brasília); só dias com as 24 horas registradas
med = {}
for cod, *_ in PLUV:
    horas = {}
    for f in sorted((HIST / cod).glob("20*.json")):
        d = json.loads(f.read_text(encoding="utf-8")); i = d["campos"].index("chuva")
        for r in d["dados"]:
            if r[i] is not None and 0 <= r[i] <= 80: horas[r[0][:13]] = r[i]
    por_dia = defaultdict(list)
    for t, v in horas.items(): por_dia[t[:10]].append(v)
    med[cod] = {dia: sum(v) for dia, v in por_dia.items() if len(v) == 24}

# previsão por dia, em cada ponto
ontem = (date.today() - timedelta(days=1)).isoformat()
prv = {m: {k: [defaultdict(float) for _ in PLUV] for k in DIAS_ANTES} for m in MODELOS}
falta = {m: {k: [defaultdict(int) for _ in PLUV] for k in DIAS_ANTES} for m in MODELOS}
for i, t in enumerate(prev["t"]):
    dia = t[:10]
    for m in MODELOS:
        for k in DIAS_ANTES:
            for j, v in enumerate(prev[m][f"d{k}"][i]):
                if v is None: falta[m][k][j][dia] += 1
                else: prv[m][k][j][dia] += v


def pares(m, k, j):
    cod = PLUV[j][0]
    return [(med[cod][d], prv[m][k][j][d]) for d in sorted(med[cod]) if INICIO <= d <= ontem and d in prv[m][k][j] and not falta[m][k][j].get(d)]


def notas(ps):
    """ps: [(medido, previsto)] por dia. Erro médio, viés, acerto dos dias de chuva forte."""
    if not ps: return None
    n = len(ps); om = sum(o for o, _ in ps); fm = sum(f for _, f in ps)
    forte = [(o, f) for o, f in ps if o >= 30]
    previu = [(o, f) for o, f in ps if f >= 30]
    mo = om / n; mf = fm / n
    cov = sum((o - mo) * (f - mf) for o, f in ps); so = math.sqrt(sum((o - mo) ** 2 for o, _ in ps)); sf = math.sqrt(sum((f - mf) ** 2 for _, f in ps))
    return {"dias": n, "erro_medio": round(sum(abs(o - f) for o, f in ps) / n, 2),
            "vies_pct": round(100 * (fm / om - 1), 1) if om else None,
            "correlacao": round(cov / (so * sf), 3) if so and sf else None,
            "dias_fortes": len(forte),
            "acerto_fortes": round(sum(f >= 20 for _, f in forte) / len(forte), 3) if forte else None,   # dia ≥ 30 mm: previu ≥ 20?
            "alarme_falso": round(sum(o < 10 for o, _ in previu) / len(previu), 3) if previu else None}  # previu ≥ 30: choveu < 10?


res = {"periodo": [INICIO, ontem], "pluviometros": [{"cod": c, "nome": n} for c, n, *_ in PLUV], "modelos": MODELOS, "notas": {}, "series": {}}
for m in MODELOS:
    res["notas"][m] = {}
    for k in DIAS_ANTES:
        por_pluv = [pares(m, k, j) for j in range(len(PLUV))]
        # média da bacia: dias em que todos os pluviômetros mediram
        dias_comuns = set.intersection(*[{d for d in med[c] if INICIO <= d <= ontem} for c, *_ in PLUV])
        bacia = []
        for d in sorted(dias_comuns):
            if all(d in prv[m][k][j] and not falta[m][k][j].get(d) for j in range(len(PLUV))):
                bacia.append((sum(med[c][d] for c, *_ in PLUV) / len(PLUV), sum(prv[m][k][j][d] for j in range(len(PLUV))) / len(PLUV)))
        res["notas"][m][f"d{k}"] = {"bacia": notas(bacia), "pontos": [notas(p) for p in por_pluv],
                                    "todos_pontos": notas([x for p in por_pluv for x in p])}

# séries diárias (média dos pluviômetros com o dia completo) para o gráfico
todos = sorted({d for c, *_ in PLUV for d in med[c] if d >= INICIO} | {t[:10] for t in prev["t"]})
for d in todos:
    ms_ = [med[c][d] for c, *_ in PLUV if d in med[c]]
    linha = {"medido": round(sum(ms_) / len(ms_), 1) if len(ms_) == len(PLUV) else None}
    for m in MODELOS:
        for k in DIAS_ANTES:
            v = [prv[m][k][j].get(d) for j in range(len(PLUV))]
            linha[f"{m}_d{k}"] = round(sum(v) / len(v), 1) if all(x is not None for x in v) and not any(falta[m][k][j].get(d) for j in range(len(PLUV))) else None
    res["series"][d] = linha

(DADOS / "avaliacao_chuva.json").write_text(json.dumps(res, ensure_ascii=False))
# versão enxuta para a página /admin do site (séries desde o início, uma lista por modelo e antecedência)
dias = sorted(d for d in res["series"] if d >= INICIO)
admin = {"periodo": res["periodo"], "atualizado": date.today().isoformat(), "modelos": MODELOS, "pluviometros": res["pluviometros"],
         "dias": dias, "medido": [res["series"][d]["medido"] for d in dias],
         "prev": {m: {f"d{k}": [res["series"][d][f"{m}_d{k}"] for d in dias] for k in DIAS_ANTES} for m in MODELOS},
         "notas": {m: {f"d{k}": {"bacia": res["notas"][m][f"d{k}"]["bacia"], "pontos": res["notas"][m][f"d{k}"]["todos_pontos"]} for k in DIAS_ANTES} for m in MODELOS}}
ADMIN = AQUI.parent.parent / "public/admin/chuva.json"
ADMIN.parent.mkdir(exist_ok=True)
ADMIN.write_text(json.dumps(admin, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"período {INICIO} a {ontem}\n")
print(f"{'modelo':34} {'dias':>5} {'erro mm':>8} {'viés %':>7} {'correl':>7} {'fortes':>7} {'acerto':>7} {'falso':>6}   (média da bacia, previsto 1 dia antes)")
for m, nome in MODELOS.items():
    n = res["notas"][m]["d1"]["bacia"]
    if n: print(f"{nome:34} {n['dias']:5} {n['erro_medio']:8} {n['vies_pct']:7} {n['correlacao']:7} {n['dias_fortes']:7} {n['acerto_fortes']!s:>7} {n['alarme_falso']!s:>6}")
