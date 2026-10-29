"""Baixa da SP Águas o histórico antigo do pluviômetro de Barro Vermelho (Lagoinha, 2E-050), de 2011 a 2023.

O site só guarda essa estação desde 2024 (public/paraitinga/historico/sp662). Para treinar a previsão,
o modelo precisa dos anos anteriores, que ficam em dados/pluv_sp662.json (chuva por hora, hora de Brasília).

Uso: python baixar_pluviometro.py
"""
import json, time, urllib.request
from datetime import datetime, timedelta
from dados import AQUI

ID_CHUVA = 661          # pluviômetro da estação Lagoinha - Barro Vermelho (sp662 no config)
URL = "https://cth.daee.sp.gov.br/sibh/api/v2/measurements"

horas = {}
for ano in range(2011, 2024):
    for mes in range(1, 13):
        ini = datetime(ano, mes, 1) + timedelta(hours=3)                       # 00h de Brasília em UTC
        fim = (datetime(ano, mes, 1) + timedelta(days=32)).replace(day=1) + timedelta(hours=3)
        url = f"{URL}?station_prefix_ids[]={ID_CHUVA}&start_date={ini:%Y-%m-%dT%H:%M}&end_date={fim:%Y-%m-%dT%H:%M}"
        for tent in range(4):
            try:
                medidas = json.load(urllib.request.urlopen(url, timeout=300))["measurements"]; break
            except Exception as e:
                print("erro", e); time.sleep(15)
        else:
            raise RuntimeError(f"não foi possível baixar {ano}-{mes:02d}")
        for m in medidas:
            if m["value"] is None: continue
            t = (datetime.strptime(m["date"], "%Y/%m/%d %H:%M") - timedelta(hours=3)).strftime("%Y-%m-%dT%H")
            horas[t] = horas.get(t, 0) + float(m["value"])
    print(ano, "ok", flush=True)

json.dump(horas, open(AQUI / "pluv_sp662.json", "w"))
print(len(horas), "horas gravadas em", AQUI / "pluv_sp662.json")
