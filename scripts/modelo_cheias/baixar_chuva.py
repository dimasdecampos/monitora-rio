from dados import AQUI
import json, urllib.request, time
PONTOS = {
  "slp":        (-23.22, -45.31),
  "lagoinha":   (-23.09, -45.19),
  "cunha":      (-23.07, -44.96),
  "cabeceiras": (-22.85, -44.85),
  "norte":      (-22.95, -45.10),
  "catucaba":   (-23.26, -45.20),
}
lat = ",".join(str(p[0]) for p in PONTOS.values()); lon = ",".join(str(p[1]) for p in PONTOS.values())
saida = {}
for ini, fim in [("2015-01-01","2018-12-31"),("2019-01-01","2022-12-31"),("2023-01-01","2026-10-25")]:
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={ini}&end_date={fim}&hourly=precipitation&timezone=America%2FSao_Paulo"
    for tent in range(4):
        try:
            d = json.load(urllib.request.urlopen(url, timeout=180)); break
        except Exception as e:
            print("erro", e); time.sleep(20)
    for nome, r in zip(PONTOS, d):
        s = saida.setdefault(nome, {"t": [], "p": []})
        s["t"] += r["hourly"]["time"]; s["p"] += r["hourly"]["precipitation"]
    print(ini, "ok", [ (r["latitude"], r["longitude"]) for r in d ])
json.dump(saida, open(AQUI / "chuva_era5.json","w"))
print({k: (len(v["t"]), round(sum(x or 0 for x in v["p"])/11.8)) for k, v in saida.items()}, "mm/ano aprox")
