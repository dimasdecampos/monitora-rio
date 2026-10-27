"""Estatísticas da régua principal de cada bacia para as visões do painel -> public/<bacia>/estatisticas.json

- sazonal: por mês, em quantos anos a régua passou de cada cota;
- recessao: depois de cada pico acima da atenção, quantas horas até voltar abaixo da atenção/alerta;
- resposta: chuva na bacia (24 h antes + 48 h depois) x subida da régua nas 72 h seguintes,
  com o quanto o solo estava encharcado. Só para bacias com "chuva_era5" no config.json; usa a
  chuva ERA5 de scripts/modelo_cheias/dados/chuva_era5.json (se o arquivo não existir, mantém a
  parte "resposta" já gravada).

Bacias sem "estatisticas" no config.json ou com régua principal sem cota de atenção são puladas.

Uso: python scripts/estatisticas.py [--bacia paraitinga]
"""
import argparse, glob, json, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402
import coletar  # noqa: E402

NOMES = {"atencao": "atenção", "alerta": "alerta", "emergencia": "emergência", "extravasamento": "transbordamento"}
ERA5 = comum.RAIZ / "scripts" / "modelo_cheias" / "dados" / "chuva_era5.json"


def mediana(v):
    s = sorted(v); n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def quantil(v, q):
    s = sorted(v); return s[min(len(s) - 1, int(q * (len(s) - 1)))] if s else None


def estatisticas(bacia):
    cfg = comum.config(bacia)
    if not cfg.get("estatisticas"):
        return
    P = cfg["principal"]
    COTAS = {k: v for k, v in comum.estacoes(cfg)[P].get("cotas_cm", {}).items() if k in NOMES}
    if "atencao" not in COTAS:
        print(f"{bacia}: régua principal sem cota de atenção, pulando"); return
    pasta = comum.pasta(bacia)
    DESTINO = pasta / cfg["estatisticas"]

    # ---------- nível horário ----------
    linhas = []
    for f in sorted(glob.glob(str(pasta / "historico" / P / "????-??.json"))):
        linhas += json.load(open(f, encoding="utf-8"))["dados"]
    linhas = coletar.sem_picos_falsos(sorted(linhas))
    H = {}
    for t, n, _, _ in linhas:   # uma leitura por hora (a última da hora)
        if n is not None: H[datetime.strptime(t[:13], "%Y-%m-%dT%H")] = n
    horas = sorted(H)
    if not horas:
        print(f"{bacia}: sem histórico de {P}"); return
    print(f"{bacia}/{P}:", len(horas), "horas,", horas[0], "a", horas[-1])

    # ---------- sazonal (usa o resumo diário, com dias completados pela régua vizinha) ----------
    diario = pasta / "historico" / P / "diario.json"
    por_dia = {datetime.strptime(r[0], "%Y-%m-%d").date(): r[3] for r in
               json.load(open(diario, encoding="utf-8"))["dados"] if r[3] is not None}
    anos_mes = {}
    for d, n in por_dia.items():
        anos_mes.setdefault((d.year, d.month), []).append(n)
    sazonal = []
    for m in range(1, 13):
        anos = [(a, v) for (a, mm), v in anos_mes.items() if mm == m and len(v) >= 20]
        item = {"mes": m, "anos": len(anos)}
        for chave in NOMES:
            item[chave] = sum(1 for _, v in anos if chave in COTAS and max(v) >= COTAS[chave])
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
                        "horas_alerta": ate_baixo(COTAS["alerta"]) if "alerta" in COTAS and n >= COTAS["alerta"] else None})
    # faixas de pico: entre as cotas (atenção, alerta e a mais alta) e os cortes extras do config
    topo = max(COTAS, key=COTAS.get)
    cortes = sorted({COTAS["atencao"], COTAS.get("alerta", COTAS["atencao"]), COTAS[topo], *cfg.get("estatisticas_cortes_cm", [])})
    nome = lambda v: next((NOMES[k] for k, c in COTAS.items() if c == v), f"{v / 100:.1f} m".replace(".", ","))
    faixas = []
    for i, lo in enumerate(cortes):
        hi = cortes[i + 1] if i + 1 < len(cortes) else 9999
        ev = [e for e in eventos if lo <= e["pico"] < hi and e["horas_atencao"]]
        if ev:
            ha = [e["horas_atencao"] for e in ev]
            faixas.append({"de": lo, "ate": hi, "nome": f"{nome(lo)} a {nome(hi)}" if hi < 9999 else f"acima de {nome(lo)}",
                           "eventos": len(ev), "mediana_h": mediana(ha), "p25_h": quantil(ha, .25), "p75_h": quantil(ha, .75)})
    print("  picos acima da atenção:", len(eventos))

    # ---------- resposta à chuva (só com chuva ERA5 da bacia) ----------
    saida_antiga = json.loads(DESTINO.read_text(encoding="utf-8")) if DESTINO.exists() else {}
    resposta = saida_antiga.get("resposta")
    pts = cfg.get("chuva_era5")
    if pts and ERA5.exists():
        d = json.load(open(ERA5))
        chuva = {datetime.strptime(t[:13], "%Y-%m-%dT%H"): sum((d[p]["p"][i] or 0) for p in pts) / len(pts) for i, t in enumerate(d[pts[0]]["t"])}
        S = lambda a, h: sum(chuva.get(a + timedelta(hours=k), 0) for k in range(h))
        pontos, solos = [], []
        t = max(horas[0], min(chuva)).replace(hour=6) + timedelta(days=1)
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
        resposta = {"descricao": "x = chuva média na bacia (ERA5) de 24 h antes até 48 h depois (mm); y = subida máxima da régua principal nas 72 h seguintes (cm); classe do solo pela chuva dos 30 dias anteriores (0 seco, 1 úmido, 2 encharcado)",
                    "solo_limites_mm": [round(t1), round(t2)], "pontos": pontos}
        print("  pontos chuva x subida:", len(pontos), "| limites do solo:", round(t1), round(t2))

    DESTINO.write_text(json.dumps({"atualizado_em": datetime.now().date().isoformat(), "estacao": P, "desde": horas[0].year,
                                   "cotas": COTAS, "sazonal": sazonal, "recessao": {"eventos": eventos, "faixas": faixas},
                                   "resposta": resposta}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("  gravado", DESTINO.relative_to(comum.RAIZ), round(DESTINO.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bacia", help="só esta bacia; padrão: todas")
    a = p.parse_args()
    for b in [a.bacia] if a.bacia else comum.bacias():
        estatisticas(b)
