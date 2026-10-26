from dados import AQUI
import json, urllib.request, time
PONTOS = [(-23.22,-45.31),(-23.09,-45.19),(-23.07,-44.96),(-22.85,-44.85),(-22.95,-45.10)]
lat = ",".join(str(p[0]) for p in PONTOS); lon = ",".join(str(p[1]) for p in PONTOS)
saida = {"t": [], "d1": [], "d2": []}
for ini, fim in [("2022-01-01","2023-06-30"),("2023-07-01","2024-12-31"),("2025-01-01","2026-10-25")]:
    url = f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation_previous_day1,precipitation_previous_day2&start_date={ini}&end_date={fim}&timezone=America%2FSao_Paulo"
    for k in range(4):
        try: d = json.load(urllib.request.urlopen(url, timeout=300)); break
        except Exception as e: print("erro", e); time.sleep(30)
    tt = d[0]["hourly"]["time"]
    for col, nome in (("precipitation_previous_day1","d1"),("precipitation_previous_day2","d2")):
        vals = []
        for i in range(len(tt)):
            v = [r["hourly"][col][i] for r in d]
            vals.append(None if any(x is None for x in v) else sum(v)/len(v))
        saida[nome] += vals
    saida["t"] += tt
    print(ini, fim, "ok")
json.dump(saida, open(AQUI / "chuva_prevista.json","w"))
anos = {}
for i, t in enumerate(saida["t"]):
    a = anos.setdefault(t[:4], [0,0,0.0,0.0]); a[0]+=1
    if saida["d1"][i] is not None: a[1]+=1; a[2]+=saida["d1"][i]
print({k:(f"{v[1]/v[0]*100:.0f}% com dados", f"{v[2]:.0f} mm") for k,v in anos.items()})
