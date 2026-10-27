"""Carrega nível horário (filtrado) e chuva ERA5 horária da bacia, alinhados por hora."""
import json, glob, importlib.util
from pathlib import Path

RAIZ = str(Path(__file__).resolve().parents[2])
AQUI = Path(__file__).resolve().parent / "dados"   # arquivos intermediários (não vão para o git)
AQUI.mkdir(exist_ok=True)

spec = importlib.util.spec_from_file_location("coletar", RAIZ + "/scripts/coletar.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

BACIA = ["slp", "lagoinha", "cunha", "cabeceiras", "norte"]


def nivel_horario(cod):
    linhas = []
    for f in sorted(glob.glob(RAIZ + f"/public/paraitinga/historico/{cod}/????-??.json")):
        linhas += json.load(open(f))["dados"]
    linhas = c.sem_picos_falsos(sorted(linhas))
    h = {}
    for t, n, v, ch in linhas:
        if n is None:
            continue
        k = t[:13]
        if k not in h or n > h[k][0]:
            h[k] = (n, v)
    return h  # "AAAA-MM-DDTHH" -> (nível cm, vazão)


def chuva_horaria():
    d = json.load(open(AQUI / "chuva_era5.json"))
    t = [x[:13] for x in d["slp"]["t"]]
    bacia = [sum((d[p]["p"][i] or 0) for p in BACIA) / len(BACIA) for i in range(len(t))]
    chapeu = [d["catucaba"]["p"][i] or 0 for i in range(len(t))]
    local = [d["slp"]["p"][i] or 0 for i in range(len(t))]
    return t, bacia, chapeu, local
