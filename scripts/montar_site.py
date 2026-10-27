"""Monta o site: copia o painel e o modo TV (pasta modelos/) para a pasta de cada bacia.

Cada bacia listada em public/bacias.json tem sua pasta (public/<id>/) com config.json e
historico/. Este script gera, em cada uma:
  index.html            <- modelos/painel.html
  tv.html               <- modelos/tv.html
  manifest.webmanifest  <- modelos/manifest.webmanifest (com o nome do rio)
e atualiza os atalhos do app (public/manifest.webmanifest, o do app da Play Store) com a
lista de bacias.

Também confere se cada config.json está coerente (régua principal existe, réguas da
cidade têm conversão etc.) e para com erro se não estiver.

Os arquivos gerados não vão para o git (.gitignore); o GitHub Actions roda este script
antes de publicar. Localmente, o server.py serve os modelos direto, sem precisar rodar.

Uso:  python scripts/montar_site.py
"""
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLIC = RAIZ / "public"
MODELOS = RAIZ / "modelos"


def bacias():
    return json.loads((PUBLIC / "bacias.json").read_text(encoding="utf-8"))["bacias"]


def conferir(cfg, pasta):
    """Lista de problemas encontrados no config.json de uma bacia."""
    erros = []
    est = {e["codigo"]: e for r in cfg.get("rios", []) for e in r["estacoes"]}
    est.update({e["codigo"]: dict(e, so_chuva=True) for e in cfg.get("pluviometros", [])})
    est.update({p["codigo"]: dict(p, so_previsao=True) for p in cfg.get("pontos_chuva", []) if p.get("codigo")})
    for campo in ("id", "rio", "cidade", "principal", "rios"):
        if not cfg.get(campo):
            erros.append(f"falta o campo '{campo}'")
    if cfg.get("id") and cfg["id"] != pasta.name:
        erros.append(f"id '{cfg['id']}' diferente do nome da pasta '{pasta.name}'")
    for campo in ("principal", "reserva", "estacao_padrao"):
        if cfg.get(campo) and cfg[campo] not in est:
            erros.append(f"{campo} '{cfg[campo]}' não está em rios[].estacoes")
    for c in cfg.get("reguas_cidade", []):
        if c not in est:
            erros.append(f"régua da cidade '{c}' não está em rios[].estacoes")
        elif c != cfg.get("principal") and c not in cfg.get("conversoes", {}):
            erros.append(f"régua da cidade '{c}' sem conversão em 'conversoes'")
    for r in cfg.get("regioes_chuva", []):
        for c in r["estacoes"]:
            if c not in est:
                erros.append(f"região de chuva '{r['nome']}': estação '{c}' não existe")
    if cfg.get("represamento") and cfg["represamento"]["afluente"] not in est:
        erros.append("represamento: afluente não existe")
    for chave in ("impactos", "estatisticas"):
        if cfg.get(chave) and not (pasta / cfg[chave]).exists() and chave != "estatisticas":
            erros.append(f"arquivo '{cfg[chave]}' não encontrado")
    if cfg.get("previsao") and not (pasta / cfg["previsao"]["modelo"]).exists():
        erros.append(f"modelo de previsão '{cfg['previsao']['modelo']}' não encontrado")
    for e in est.values():
        if e.get("fonte") == "spaguas" and not e.get("id_nivel") and not (e.get("so_chuva") and e.get("id_chuva")):
            erros.append(f"{e['codigo']}: estação da SP Águas sem 'id_nivel' (ou pluviômetro sem 'id_chuva')")
        if not e.get("lat") or not e.get("lon"):
            erros.append(f"{e['codigo']}: sem coordenadas")
    return erros


def atalhos_do_app():
    """Atalhos do ícone do app (toque longo): um por bacia, na ordem de bacias.json."""
    arq = PUBLIC / "manifest.webmanifest"
    m = json.loads(arq.read_text(encoding="utf-8"))
    m["shortcuts"] = [{"name": f"{b['rio']} — {b['cidade']}", "short_name": b["rio"].replace("Rio ", ""), "url": f"./{b['id']}/",
                       "icons": [{"src": "icones/icone-192.png", "sizes": "192x192", "type": "image/png"}]} for b in bacias()]
    arq.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    problemas = 0
    manifesto = json.loads((MODELOS / "manifest.webmanifest").read_text(encoding="utf-8"))
    for b in bacias():
        pasta = PUBLIC / b["id"]
        cfg = json.loads((pasta / "config.json").read_text(encoding="utf-8"))
        erros = conferir(cfg, pasta)
        for e in erros:
            print(f"[{b['id']}] {e}")
        problemas += len(erros)
        shutil.copyfile(MODELOS / "painel.html", pasta / "index.html")
        shutil.copyfile(MODELOS / "tv.html", pasta / "tv.html")
        m = dict(manifesto, name=f"{cfg['rio']} — {cfg['cidade']}", short_name=cfg["rio"],
                 description=f"Nível, chuva e avisos de cheia do {cfg['rio']} em {cfg['cidade']}.")
        (pasta / "manifest.webmanifest").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{b['id']}: painel, modo TV e manifesto prontos")
    atalhos_do_app()
    if problemas:
        sys.exit(f"{problemas} problema(s) nas configurações")


if __name__ == "__main__":
    main()
