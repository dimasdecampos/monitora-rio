"""Baixa a chuva horária estimada (ERA5, Open-Meteo) nos pontos de uma bacia, para as estatísticas.

Lê config.json → "pontos_chuva" (com "codigo") e grava em
scripts/modelo_cheias/dados/<config.chuva_era5.arquivo>, no mesmo formato de chuva_era5.json:
{ "<codigo>": {"t": [...], "p": [...]}, ... }. A pasta dados/ não vai para o git.

Uso: python scripts/baixar_chuva_era5.py --bacia paraibuna [--desde 2015-01-01]
Depois: python scripts/estatisticas.py --bacia paraibuna
"""
import argparse, json, sys, time, urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

DADOS = comum.RAIZ / "scripts" / "modelo_cheias" / "dados"


def main():
    a = argparse.ArgumentParser(); a.add_argument("--bacia", required=True); a.add_argument("--desde", default="2015-01-01")
    args = a.parse_args()
    cfg = comum.config(args.bacia)
    pts = [p for p in cfg.get("pontos_chuva", []) if p.get("codigo")]
    if not pts or not isinstance(cfg.get("chuva_era5"), dict):
        sys.exit("a bacia precisa de pontos_chuva (com codigo) e de chuva_era5: {arquivo, pontos}")
    lat = ",".join(str(p["lat"]) for p in pts); lon = ",".join(str(p["lon"]) for p in pts)
    fim_total = date.today() - timedelta(days=6)   # o ERA5 chega com alguns dias de atraso
    ini = date.fromisoformat(args.desde); saida = {}
    while ini <= fim_total:
        fim = min(date(ini.year + 3, 12, 31), fim_total)
        url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
               f"&start_date={ini}&end_date={fim}&hourly=precipitation&timezone=America%2FSao_Paulo")
        for tent in range(4):
            try:
                d = json.load(urllib.request.urlopen(url, timeout=300)); break
            except Exception as e:
                print("erro", e); time.sleep(30)
        else:
            sys.exit("Open-Meteo não respondeu")
        for p, r in zip(pts, d if isinstance(d, list) else [d]):
            s = saida.setdefault(p["codigo"], {"t": [], "p": []})
            s["t"] += r["hourly"]["time"]; s["p"] += r["hourly"]["precipitation"]
        print(ini, "a", fim, "ok")
        ini = fim + timedelta(days=1)
    DADOS.mkdir(parents=True, exist_ok=True)
    destino = DADOS / cfg["chuva_era5"]["arquivo"]
    json.dump(saida, open(destino, "w"))
    anos = max(1, (fim_total - date.fromisoformat(args.desde)).days / 365.25)
    print(destino.name, {k: round(sum(x or 0 for x in v["p"]) / anos) for k, v in saida.items()}, "mm/ano")


if __name__ == "__main__":
    main()
