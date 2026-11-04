"""Confere se o painel (modelos/painel.html) e o robô de avisos (scripts/alertas.py) calculam a mesma
chance de cheia. A conta existe nos dois lugares; se um mudar sem o outro, o site mostra uma chance e o
robô avisa por outra.

Tira chanceDeSubir/chanceDeChegar do painel, roda no Node com casos variados (todas as versões do modelo,
níveis quebrados, rio subindo e descendo rio acima) e compara com alertas.calculadora.
Também confere se o gatilho rio acima do config.json aponta para uma régua que existe.

Uso: python scripts/testar_previsao.py   (precisa do Node; para com erro se houver diferença)
"""
import json, random, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import alertas, comum  # noqa: E402

html = (RAIZ / "modelos/painel.html").read_text(encoding="utf-8")
ini, fim = html.index("const sigmoide"), html.index("async function buscarPrevisao")
funcoes = html[ini:fim]

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

sys.exit(f"{erros} problema(s)" if erros else 0)
