"""Baixa da Open-Meteo vento, umidade e energia de tempestade (CAPE) no litoral e na serra,
para testar se ajudam a prever cheias (testar_atmosfera.py).

Pontos: litoral (Ubatuba) e serra (Cunha). Três fontes, gravadas em dados/ (fora do git):
  atm_era5.json       ERA5 2015 → hoje: vento 10 m e água precipitável (TCWV)    → treino
  atm_hist.json       previsões históricas 2022 → hoje: CAPE, vento 10 m e 850 hPa → diagnóstico/treino do CAPE
  atm_prev.json       previsões feitas 1 e 2 dias antes, 2024 → hoje: CAPE e vento 10 m → teste honesto
Horas no fuso de Brasília, como chuva_era5.json e chuva_prevista7.json.

Uso: python baixar_atmosfera.py
"""
import json, time, urllib.request
from datetime import date
from dados import AQUI

PONTOS = {"litoral": (-23.43, -45.07), "serra": (-23.07, -44.96)}
LAT = ",".join(str(p[0]) for p in PONTOS.values()); LON = ",".join(str(p[1]) for p in PONTOS.values())
HOJE = date.today().isoformat()


def baixar(base, variaveis, blocos, arquivo):
    saida = {nome: {"t": [], **{v: [] for v in variaveis}} for nome in PONTOS}
    for ini, fim in blocos:
        url = (f"{base}?latitude={LAT}&longitude={LON}&hourly={','.join(variaveis)}"
               f"&start_date={ini}&end_date={fim}&timezone=America%2FSao_Paulo")
        for tent in range(4):
            try:
                d = json.load(urllib.request.urlopen(url, timeout=600)); break
            except Exception as e:
                print("  erro", e); time.sleep(30)
        else:
            raise RuntimeError(f"não baixou {arquivo} {ini}")
        for nome, r in zip(PONTOS, d if isinstance(d, list) else [d]):
            s = saida[nome]; s["t"] += r["hourly"]["time"]
            for v in variaveis: s[v] += r["hourly"][v]
        print(arquivo, ini, fim, "ok", flush=True)
    json.dump(saida, open(AQUI / arquivo, "w"))
    n = saida["litoral"]
    print(arquivo, {v: sum(x is not None for x in n[v]) for v in variaveis}, "horas com dado")


anos = lambda a, b: [(f"{y}-01-01", min(f"{y}-12-31", HOJE)) for y in range(a, b + 1)]
fim = int(HOJE[:4])
baixar("https://archive-api.open-meteo.com/v1/archive",
       ["wind_speed_10m", "wind_direction_10m", "total_column_integrated_water_vapour"], anos(2015, fim), "atm_era5.json")
baixar("https://historical-forecast-api.open-meteo.com/v1/forecast",
       ["cape", "wind_speed_10m", "wind_direction_10m", "wind_speed_850hPa", "wind_direction_850hPa", "relative_humidity_850hPa"],
       anos(2022, fim), "atm_hist.json")
baixar("https://previous-runs-api.open-meteo.com/v1/forecast",
       [f"{v}_previous_day{k}" for k in (1, 2) for v in ("cape", "wind_speed_10m", "wind_direction_10m")],
       anos(2024, fim), "atm_prev.json")
