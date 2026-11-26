"""Confere se o painel (modelos/painel.html) e o robô de avisos (scripts/alertas.py) calculam a mesma
chance de cheia. A conta existe nos dois lugares; se um mudar sem o outro, o site mostra uma chance e o
robô avisa por outra.

Tira chanceDeSubir/chanceDeChegar do painel, roda no Node com casos variados (todas as versões do modelo,
níveis quebrados, rio subindo e descendo rio acima) e compara com alertas.calculadora.
Também confere se o gatilho rio acima do config.json aponta para uma régua que existe.

Uso: python scripts/testar_previsao.py   (precisa do Node; para com erro se houver diferença)
"""
import json, random, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import alertas, comum  # noqa: E402

html = (RAIZ / "modelos/painel.html").read_text(encoding="utf-8")
ini, fim = html.index("const sigmoide"), html.index("async function buscarPrevisao")
funcoes = html[ini:fim]

ini_l, fim_l = html.index("function tendenciaAtual"), html.index("function faixaTipica")
funcoes_linha = html[ini_l:fim_l]


def conferir_linha(bacia, P, modelo):
    """Confere a linha de previsão (linhaPrevista no painel × alertas.trajetoria no robô), que o robô
    grava no Supabase para comparar depois com o que o rio fez. Devolve quantos problemas achou."""
    if not modelo["passarela"].get("trajetoria"): return 0
    rnd = random.Random(2); casos = []
    for k in range(40):
        t1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(hours=rnd.randint(0, 24 * 300), minutes=rnd.choice([0, 10, 20, 30, 40, 50]))
        h_ini = (t1.astimezone(alertas.BRT).replace(minute=0) - timedelta(days=31)).replace(tzinfo=None)
        tempo = [(h_ini + timedelta(hours=j)).strftime("%Y-%m-%dT%H:00") for j in range(39 * 24)]
        media = [rnd.choice([0, 0, 0, rnd.uniform(0, 3), rnd.uniform(0, 15)]) for _ in tempo]
        base, sobe = rnd.uniform(80, 420), rnd.choice([0, rnd.uniform(-8, 12)])
        serie = [(t1 - timedelta(minutes=10 * n), base - sobe * n / 6 + rnd.uniform(-.5, .5)) for n in range(84, -1, -1)]
        versao = rnd.choice(["A", "B", "BP"]); dc6 = rnd.uniform(-40, 120)
        agora = t1 + timedelta(minutes=rnd.choice([3, 30, 150]))
        ctx = dict(tempo=tempo, media=media, versao=versao, dc6=dc6)
        py = alertas.trajetoria(modelo, serie, ctx, agora)
        casos.append(dict(tempo=tempo, media=media, ref={"H0": serie[-1][1], "t": t1.timestamp() * 1000, **({"dc6": dc6} if "B" in versao else {})},
                          leituras=[{"t": t.isoformat(), "nivel": v} for t, v in serie], agora=agora.timestamp() * 1000,
                          py=[list(p) for p in py] if py else None))
    js = f"""const pad = n => String(n).padStart(2, "0");
const horaLocal = d => `${{d.getFullYear()}}-${{pad(d.getMonth() + 1)}}-${{pad(d.getDate())}}T${{pad(d.getHours())}}:00`;
const comNivel = ls => ls.filter(l => l.nivel != null), ms = l => new Date(l.t).getTime();
const P = {json.dumps(P)}, REGUAS_CIDADE = [P], estado = {{ estacao: P }}, config = {{ conversoes: {{}} }};
const prev = {{ modelo: {json.dumps(modelo)} }}, cache = {{}};
{funcoes_linha}
const casos = {json.dumps([{k: v for k, v in c.items() if k != "py"} for c in casos])};
console.log(JSON.stringify(casos.map(c => {{
  prev.ref = c.ref; prev.dados = {{ tempo: c.tempo, media: c.media }}; cache[P] = {{ leituras: c.leituras }}; Date.now = () => c.agora;
  const u = c.leituras.at(-1), r = linhaPrevista({{ x: ms(u), y: u.nivel / 100 }});
  return r && r.pts.slice(1).map(p => [Math.round((p.x - ms(u)) / 36e5), p.lo, p.md, p.hi]);
}})));"""
    import os
    r = subprocess.run(["node", "-"], input=js, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "TZ": "America/Sao_Paulo"})
    if r.returncode:
        print(f"{bacia}: erro ao rodar a linha do painel no Node:\n{r.stderr}"); return 1
    probs, pior = 0, 0
    for c, pj in zip(casos, json.loads(r.stdout)):
        if (pj is None) != (c["py"] is None) or (pj and len(pj) != len(c["py"])):
            print(f"{bacia}: linha com tamanho diferente: painel {pj and len(pj)}, robô {c['py'] and len(c['py'])}"); probs += 1; continue
        for a, b in zip(pj or [], c["py"] or []):
            d = max(abs(x - y) for x, y in zip(a, b)); pior = max(pior, d)
            if d > 1e-9:
                if probs < 5: print(f"{bacia}: linha diferente em {a[0]} h: painel {a[1:]}, robô {b[1:]}")
                probs += 1; break
    print(f"{bacia}: linha de previsão, {len(casos)} casos, maior diferença painel × robô {pior:.1e} m")
    return probs


erros = 0
for bacia in comum.bacias():
    cfg = comum.config(bacia)
    if not cfg.get("previsao"): continue
    modelo = json.loads((comum.pasta(bacia) / cfg["previsao"]["modelo"]).read_text(encoding="utf-8"))
    pm = modelo.get("passarela")
    if not pm: continue
    gat = cfg["previsao"].get("gatilho")
    if gat:
        est = comum.estacoes(cfg)
        if gat["estacao"] not in est or not {"sobe_cm", "horas"} <= gat.keys():
            print(f"{bacia}: gatilho mal configurado: {gat}"); erros += 1

    rnd = random.Random(1); casos = []
    versoes = [v for v in ("A", "B", "P", "BP") if f"pesos_{v}" in pm]
    for k in range(200):
        versao = versoes[k % len(versoes)]
        x = dict(H0=rnd.uniform(60, 400), p24=rnd.choice([0, rnd.uniform(0, 120)]), p72=rnd.uniform(0, 250),
                 api=rnd.uniform(0, 400), f48=rnd.choice([0, rnd.uniform(0, 150)]), versao=versao,
                 dc6=rnd.uniform(-40, 120), dc12=rnd.uniform(-60, 180),
                 pluv={f"l{h}": rnd.uniform(0, 30 * h ** .5) for h in (6, 12, 24, 72)})
        x["L"] = x["H0"] + rnd.choice([5, 37.5, rnd.uniform(0, 350)])
        casos.append(x)

    js = f"""const prev = {{ modelo: {json.dumps(modelo)} }};
{funcoes}
const casos = {json.dumps(casos)};
console.log(JSON.stringify(casos.map(c => chanceDeChegar(c.H0, c, c.f48, c.L))));"""
    r = subprocess.run(["node", "-"], input=js, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print(f"{bacia}: erro ao rodar o painel no Node:\n{r.stderr}"); erros += 1; continue
    painel = json.loads(r.stdout)
    pior = 0
    for c, pj in zip(casos, painel):
        chance = alertas.calculadora(pm, c["versao"], c["H0"], c["f48"], c["p24"], c["p72"], c["api"], c["dc6"], c["dc12"], c["pluv"])
        pp = chance(c["L"] - c["H0"])
        pior = max(pior, abs(pp - pj))
        if abs(pp - pj) > 1e-9 and erros < 10:
            print(f"{bacia}: diferença na versão {c['versao']}: painel {pj:.6f}, robô {pp:.6f} (H0 {c['H0']:.1f}, alvo {c['L']:.1f})")
            erros += 1
    print(f"{bacia}: {len(casos)} casos, maior diferença painel × robô {pior:.1e}")
    erros += conferir_linha(bacia, cfg["principal"], modelo)

sys.exit(f"{erros} problema(s)" if erros else 0)
