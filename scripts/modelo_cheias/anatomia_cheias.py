"""Engenharia reversa das cheias na Passarela: como a onda desce o rio até São Luiz.

Por quê: na cheia de 26–27/11/2026 a linha rio acima (rio_acima.py) pôs o pico 2–3 h à frente em toda rodada
enquanto a Passarela seguia subindo. Este script mede, nas cheias de 2020 em diante (histórico do site):

  1. retrato de cada cheia: pico, de onde partiu, horas de subida, horas perto do pico (platô), descida em 12 h
     e, para cada régua rio acima com dados, o pico dela, quantas horas antes do pico da Passarela e o nível
     dela na hora do pico da Passarela;
  2. tempo de viagem: o atraso que melhor liga a variação em 3 h de cada régua à da Passarela (rio alto);
  3. hora a hora, nas cheias escolhidas: Passarela, Estrada do Ribeira 4 h antes e a diferença entre elas.

Resultado (nov/2026): atrasos de 4 h (Estrada do Ribeira, correlação 0,94), 8 h (Barro Vermelho), 11 h
(Lagoinha–Jacuí), 14 h (Rio Jacuí) e 22 h (Cunha). Na subida das cheias grandes a Passarela fica 60–67 cm
abaixo da Estrada do Ribeira de 4 h antes e só para de subir quando ela baixa: pico 4–9 h depois do pico da
Estrada do Ribeira, 41–70 cm abaixo dele (diferença menor nas cheias maiores).

Uso: python anatomia_cheias.py [AAAA-MM-DD ...]   (datas das cheias para a tabela hora a hora; padrão: jan, fev e nov/2026)
"""
import json, glob, math, sys
from datetime import datetime as D, timedelta as TD
from dados import RAIZ

REGUAS = {"E": ("sp35388", "Estrada do Ribeira"), "B": ("sp662", "Barro Vermelho"), "J": ("sp35402", "Lagoinha–Jacuí"),
          "Jc": ("sp820", "Rio Jacuí"), "C": ("sp818", "Cunha")}
PICO_MIN, DESDE = 230, "2020"   # cheias: picos da Passarela acima disso, separados por 4 dias


def serie(cod):
    d = {}
    for f in sorted(glob.glob(f"{RAIZ}/public/paraitinga/historico/{cod}/????-??.json")):
        for t, n, *_ in json.load(open(f, encoding="utf-8"))["dados"]:
            if n is not None: d[t[:13]] = n
    return d


hora = lambda t: t.strftime("%Y-%m-%dT%H")
P = serie("sp664")
S = {k: serie(c) for k, (c, _) in REGUAS.items()}


def cheias():
    ts, ev = sorted(P), []
    for i, t in enumerate(ts):
        if P[t] < PICO_MIN or t < DESDE: continue
        if P[t] >= max(P[u] for u in ts[max(0, i - 48):i + 49]) and (not ev or (D.fromisoformat(t) - D.fromisoformat(ev[-1])).total_seconds() > 96 * 3600):
            ev.append(t)
    return ev


def retrato():
    print(f"{'pico':14} {'P':>4} {'base':>4} {'sobe':>4} {'platô':>5} {'cm/h':>5} {'desce12':>7} | régua: pico / horas antes / nível no pico da Passarela")
    for t in cheias():
        T, pk = D.fromisoformat(t), P[t]
        base = min((P[u], u) for u in (hora(T + TD(hours=h)) for h in range(-72, 1)) if u in P)
        sobe = (T - D.fromisoformat(base[1])).total_seconds() / 3600
        plato = sum(P.get(hora(T + TD(hours=h)), -1) >= pk - 10 for h in range(-48, 49))
        r6 = (pk - P.get(hora(T - TD(hours=6)), pk)) / 6
        desce = pk - P.get(hora(T + TD(hours=12)), pk)
        s = f"{t:14} {pk:4.0f} {base[0]:4.0f} {sobe:4.0f} {plato:5d} {r6:5.1f} {desce:7.0f} |"
        for g, sg in S.items():
            w = [(sg[u], u) for u in (hora(T + TD(hours=h)) for h in range(-60, 7)) if u in sg]
            if len(w) < 30: continue
            m = max(w); agora = sg.get(t)
            s += f" {g}:{m[0]:.0f}/{(T - D.fromisoformat(m[1])).total_seconds() / 3600:.0f}h/{agora:.0f}" if agora is not None else f" {g}:{m[0]:.0f}/{(T - D.fromisoformat(m[1])).total_seconds() / 3600:.0f}h/-"
        print(s)


def tempo_de_viagem():
    t0 = D(int(DESDE), 1, 1)
    hrs = [hora(t0 + TD(hours=h)) for h in range(int((D.fromisoformat(max(P)) - t0).total_seconds() // 3600))]
    def d3(s, i):
        a, b = s.get(hrs[i]), s.get(hrs[i - 3])
        return None if a is None or b is None else a - b
    for g, sg in S.items():
        melhor = []
        for lag in range(61):
            xs, ys = [], []
            for i in range(lag + 3, len(hrs)):
                if P.get(hrs[i], 0) < 150: continue   # só rio alto
                dp, dg = d3(P, i), d3(sg, i - lag)
                if dp is None or dg is None: continue
                xs.append(dg); ys.append(dp)
            if len(xs) < 200: continue
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            melhor.append((cov / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)), lag, len(xs)))
        if melhor:
            r, lag, n = max(melhor)
            print(f"{REGUAS[g][1]:20} atraso {lag:2d} h (correlação {r:.2f}, {n} horas)")


def hora_a_hora(dia):
    T = D.fromisoformat(dia) - TD(hours=12)
    print(f"== {dia}  (P−E4: Passarela menos Estrada do Ribeira 4 h antes)")
    for h in range(0, 60, 2):
        t, t4 = hora(T + TD(hours=h)), hora(T + TD(hours=h - 4))
        if t not in P: continue
        f = lambda v: f"{v:4.0f}" if v is not None else "   -"
        p, e4 = P.get(t), S["E"].get(t4)
        print(f"{t[5:]} P{f(p)} E{f(S['E'].get(t))} E(−4h){f(e4)} P−E4{f(p - e4 if e4 is not None else None)} B{f(S['B'].get(t))} C{f(S['C'].get(t))}")


if __name__ == "__main__":
    print("1) Retrato das cheias\n"); retrato()
    print("\n2) Tempo de viagem até a Passarela\n"); tempo_de_viagem()
    print("\n3) Hora a hora\n")
    for d in sys.argv[1:] or ["2026-01-27", "2026-02-08", "2026-11-27"]: hora_a_hora(d)
