"""Previsões arquivadas de chuva (feitas 1 a 7 dias antes) para a bacia, 2024 → hoje."""
from dados import AQUI
import json, urllib.request, time
from datetime import date
PONTOS = [(-23.22, -45.31), (-23.09, -45.19), (-23.07, -44.96), (-22.85, -44.85), (-22.95, -45.10)]
lat = ",".join(str(p[0]) for p in PONTOS); lon = ",".join(str(p[1]) for p in PONTOS)
cols = [f"precipitation_previous_day{k}" for k in range(1, 8)]
saida = {"t": [], **{f"d{k}": [] for k in range(1, 8)}}
hoje = date.today().isoformat()
for ini, fim in [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", hoje)]:
    url = (f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&hourly={','.join(cols)}&start_date={ini}&end_date={fim}&timezone=America%2FSao_Paulo")
    for k in range(4):
        try: d = json.load(urllib.request.urlopen(url, timeout=600)); break
        except Exception as e: print("erro", e); time.sleep(30)
    tt = d[0]["hourly"]["time"]
    for k in range(1, 8):
        col = f"precipitation_previous_day{k}"
        for i in range(len(tt)):
            v = [r["hourly"][col][i] for r in d]
            saida[f"d{k}"].append(None if any(x is None for x in v) else sum(v) / len(v))
    saida["t"] += tt
    print(ini, fim, "ok")
json.dump(saida, open(AQUI / "chuva_prevista7.json", "w"))
print({f"d{k}": sum(v is not None for v in saida[f"d{k}"]) for k in range(1, 8)}, "horas com dado")
