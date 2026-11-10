"""Previsões arquivadas de chuva (feitas 1 e 2 dias antes) de 8 modelos de tempo, nos 5 pontos da bacia
do Paraitinga, 2024 → out/2026. Para o teste "outro modelo de tempo" de testar_ideias.py.

Grava dados/prev_modelos.json: {"t": [...], modelo: {"d1": [[5 pontos] por hora], "d2": [...]}}.

Uso: python baixar_prev_modelos.py
"""
import json, urllib.request, time
from dados import AQUI

PONTOS = [(-23.22, -45.31), (-23.09, -45.19), (-23.07, -44.96), (-22.85, -44.85), (-22.95, -45.10)]
MODELOS = ["best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_global", "meteofrance_seamless",
           "jma_seamless", "cma_grapes_global"]
lat = ",".join(str(p[0]) for p in PONTOS); lon = ",".join(str(p[1]) for p in PONTOS)
saida = {"t": [], **{m: {"d1": [], "d2": []} for m in MODELOS}}
for ini, fim in [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-10-26")]:
    url = (f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&hourly=precipitation_previous_day1,precipitation_previous_day2&start_date={ini}&end_date={fim}"
           f"&timezone=America%2FSao_Paulo&models={','.join(MODELOS)}")
    for k in range(4):
        try: d = json.load(urllib.request.urlopen(url, timeout=600)); break
        except Exception as e: print("erro", e, flush=True); time.sleep(30)
    else:
        raise RuntimeError(f"não foi possível baixar {ini} a {fim}")
    tt = d[0]["hourly"]["time"]
    for m in MODELOS:
        for k in (1, 2):
            col = f"precipitation_previous_day{k}_{m}"
            saida[m][f"d{k}"] += [[r["hourly"][col][i] for r in d] for i in range(len(tt))]
    saida["t"] += tt
    print(ini, fim, "ok", flush=True)
json.dump(saida, open(AQUI / "prev_modelos.json", "w"))
for m in MODELOS: print(m, sum(all(x is not None for x in v) for v in saida[m]["d1"]), "horas com dado (1 dia antes)")
