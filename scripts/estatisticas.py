"""Estatísticas da Passarela para as visões do painel -> public/estatisticas.json

- sazonal: por mês, em quantos anos a Passarela passou de cada cota oficial (2018 → hoje);
- recessao: depois de cada pico acima da atenção, quantas horas até voltar abaixo da atenção/alerta;
- resposta: chuva na bacia (24 h antes + 48 h depois) x subida da Passarela nas 72 h seguintes,
  com o quanto o solo estava encharcado. Usa a chuva ERA5 de scripts/modelo_cheias/dados/chuva_era5.json
  (se o arquivo não existir, mantém a parte "resposta" já gravada).

Uso: python scripts/estatisticas.py
"""
import glob, json, importlib.util
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("coletar", RAIZ / "scripts" / "coletar.py")
coletar = importlib.util.module_from_spec(spec); spec.loader.exec_module(coletar)
config = json.loads((RAIZ / "public" / "config.json").read_text(encoding="utf-8"))
COTAS = {e["codigo"]: e for r in config["rios"] for e in r["estacoes"]}["sp664"]["cotas_cm"]
DESTINO = RAIZ / "public" / "estatisticas.json"


def mediana(v):
    s = sorted(v); n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def quantil(v, q):
    s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))] if s else None


# ---------- nível horário da Passarela ----------
linhas = []
for f in sorted(glob.glob(str(RAIZ / "public" / "historico" / "sp664" / "????-??.json"))):
    linhas += json.load(open(f, encoding="utf-8"))["dados"]
linhas = coletar.sem_picos_falsos(sorted(linhas))
H = {datetime.strptime(t[:13], "%Y-%m-%dT%H"): n for t, n, _, _ in linhas if n is not None}
horas = sorted(H)
print("Passarela:", len(horas), "horas,", horas[0], "a", horas[-1])

# ---------- sazonal ----------
# usa o resumo diário (dias sem leitura da Passarela já completados com a régua da ANA)
por_dia = {datetime.strptime(r[0], "%Y-%m-%d").date(): r[3] for r in
           json.load(open(RAIZ / "public" / "historico" / "sp664" / "diario.json", encoding="utf-8"))["dados"] if r[3] is not None}
anos_mes = {}
for d, n in por_dia.items():
    k = (d.year, d.month); anos_mes.setdefault(k, []).append(n)
sazonal = []
for m in range(1, 13):
    anos = [(a, v) for (a, mm), v in anos_mes.items() if mm == m and len(v) >= 20]
    item = {"mes": m, "anos": len(anos)}
    for chave in ("atencao", "alerta", "emergencia", "extravasamento"):
        item[chave] = sum(1 for _, v in anos if max(v) >= COTAS[chave])
    sazonal.append(item)

# ---------- recessão (picos acima da atenção) ----------
eventos, ultimo = [], None
for t in horas:
    n = H[t]
    if n < COTAS["atencao"]: continue
    janela = [H[x] for x in (t + timedelta(hours=h) for h in range(-48, 49)) if x in H]
    if n < max(janela) or (ultimo and (t - ultimo).total_seconds() < 72 * 3600): continue
    ultimo = t
    def ate_baixo(limite):
        for h in range(1, 24 * 15):
            x = t + timedelta(hours=h)
            if x in H and H[x] < limite: return h
        return None
    eventos.append({"data": t.strftime("%Y-%m-%dT%H"), "pico": round(n), "horas_atencao": ate_baixo(COTAS["atencao"]),
                    "horas_alerta": ate_baixo(COTAS["alerta"]) if n >= COTAS["alerta"] else None})
faixas = []
for lo, hi, nome in ((COTAS["atencao"], COTAS["alerta"], "até o alerta"), (COTAS["alerta"], COTAS["extravasamento"], "alerta a transbordamento"),
                     (COTAS["extravasamento"], 450, "transbordamento até 4,5 m"), (450, 9999, "acima de 4,5 m")):
    ev = [e for e in eventos if lo <= e["pico"] < hi and e["horas_atencao"]]
    if ev:
        ha = [e["horas_atencao"] for e in ev]
        faixas.append({"de": lo, "ate": hi, "nome": nome, "eventos": len(ev), "mediana_h": mediana(ha), "p25_h": quantil(ha, .25), "p75_h": quantil(ha, .75)})
print("picos acima da atenção:", len(eventos))

# ---------- resposta à chuva ----------
saida_antiga = json.loads(DESTINO.read_text(encoding="utf-8")) if DESTINO.exists() else {}
resposta = saida_antiga.get("resposta")
era5 = RAIZ / "scripts" / "modelo_cheias" / "dados" / "chuva_era5.json"
if era5.exists():
    d = json.load(open(era5))
    pts = ["slp", "lagoinha", "cunha", "cabeceiras", "norte"]
    chuva = {datetime.strptime(t[:13], "%Y-%m-%dT%H"): sum((d[p]["p"][i] or 0) for p in pts) / len(pts) for i, t in enumerate(d["slp"]["t"])}
    S = lambda a, h: sum(chuva.get(a + timedelta(hours=k), 0) for k in range(h))
    pontos, solos = [], []
    t = datetime(2018, 1, 2, 6)
    fim = min(max(chuva), horas[-1]) - timedelta(hours=72)
    while t <= fim:
        if t in H:
            fut = [H[x] for x in (t + timedelta(hours=h) for h in range(1, 73)) if x in H]
            if len(fut) >= 60:
                x = S(t - timedelta(hours=24), 72)            # 24 h antes + 48 h depois
                solo = S(t - timedelta(hours=24 + 720), 720)  # 30 dias antes
                pontos.append([round(x, 1), round(max(fut) - H[t]), round(solo)]); solos.append(solo)
        t += timedelta(hours=24)
    t1, t2 = quantil(solos, 1 / 3), quantil(solos, 2 / 3)
    for p in pontos: p[2] = 0 if p[2] < t1 else 1 if p[2] < t2 else 2
    resposta = {"descricao": "x = chuva média na bacia (ERA5) de 24 h antes até 48 h depois (mm); y = subida máxima da Passarela nas 72 h seguintes (cm); classe do solo pela chuva dos 30 dias anteriores (0 seco, 1 úmido, 2 encharcado)",
                "solo_limites_mm": [round(t1), round(t2)], "pontos": pontos}
    print("pontos chuva x subida:", len(pontos), "| limites do solo:", round(t1), round(t2))

DESTINO.write_text(json.dumps({"atualizado_em": datetime.now().date().isoformat(), "cotas": COTAS, "sazonal": sazonal,
                               "recessao": {"eventos": eventos, "faixas": faixas}, "resposta": resposta},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("gravado", DESTINO, round(DESTINO.stat().st_size / 1024), "KB")
for f in faixas: print(" ", f)
