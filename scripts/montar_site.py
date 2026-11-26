"""Monta o site: copia o painel e o modo TV (pasta modelos/) para a pasta de cada bacia.

Cada bacia listada em public/bacias.json tem sua pasta (public/<id>/) com config.json e
historico/. Este script gera, em cada uma:
  index.html            <- modelos/painel.html (com título, descrição e prévia de link do rio, para o Google e o WhatsApp)
  tv.html               <- modelos/tv.html
  manifest.webmanifest  <- modelos/manifest.webmanifest (com o nome do rio)
e atualiza os atalhos do app (public/manifest.webmanifest, o do app da Play Store) com a
lista de bacias. Gera também public/sitemap.xml (para o Google) com as páginas públicas.

Também confere se cada config.json está coerente (régua principal existe, réguas da
cidade têm conversão etc.) e para com erro se não estiver.

Os arquivos gerados não vão para o git (.gitignore); o GitHub Actions roda este script
antes de publicar. Localmente, o server.py serve os modelos direto, sem precisar rodar.

Uso:  python scripts/montar_site.py
"""
import html
import json
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLIC = RAIZ / "public"
MODELOS = RAIZ / "modelos"
SITE = "https://rio.slparaitinga.com/"


def textos_seo(cfg):
    """Título e descrição do painel de um rio (o painel repete o mesmo título pelo JavaScript)."""
    titulo = f"{cfg['rio']} hoje: nível e cheias em {cfg['cidade']}"
    descricao = (f"Nível do {cfg['rio']} em {cfg['cidade']} agora: régua em tempo real, chuva na bacia, "
                 f"previsão de cheia e avisos no celular. Dados oficiais da SP Águas e da ANA.")
    return titulo, descricao


def painel_com_seo(modelo, b, cfg):
    """Troca o título e a descrição genéricos do modelo pelos do rio e põe endereço canônico, prévia de link
    (WhatsApp, Facebook) e dados estruturados. Bacias ocultas ficam fora do Google (noindex)."""
    titulo, descricao = textos_seo(cfg)
    url = f"{SITE}{b['id']}/"
    t, d = html.escape(titulo), html.escape(descricao)
    antigo_t, antigo_d = "<title>Monitor do Rio</title>", '<meta name="description" content="Nível, chuva, previsão e avisos de cheia em tempo real, com dados da SP Águas e da ANA">'
    if antigo_t not in modelo or antigo_d not in modelo:
        sys.exit("modelos/painel.html: título ou descrição mudaram; atualize painel_com_seo em montar_site.py")
    dados = {"@context": "https://schema.org", "@type": "WebPage", "name": titulo, "description": descricao, "url": url,
             "inLanguage": "pt-BR", "isPartOf": {"@type": "WebSite", "name": "Monitor dos Rios", "url": SITE},
             "about": {"@type": "RiverBodyOfWater", "name": cfg["rio"],
                       "containedInPlace": {"@type": "City", "name": cfg["cidade"], "address": {"@type": "PostalAddress", "addressRegion": "SP", "addressCountry": "BR"}}}}
    extra = "\n".join(filter(None, [
        f'<link rel="canonical" href="{url}">',
        '<meta name="robots" content="noindex">' if b.get("oculta") else "",
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Monitor dos Rios">',
        '<meta property="og:locale" content="pt_BR">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:image" content="{SITE}divulgacao/painel.jpg">',
        '<meta property="og:image:width" content="1000"><meta property="og:image:height" content="1160">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<script type="application/ld+json">{json.dumps(dados, ensure_ascii=False)}</script>',
    ]))
    h1 = '<h1 class="so-leitor" id="tituloPagina">Nível do rio em tempo real</h1>'
    if h1 not in modelo:
        sys.exit("modelos/painel.html: o título da página (h1) mudou; atualize painel_com_seo em montar_site.py")
    return (modelo.replace(antigo_t, f"<title>{t}</title>", 1)
            .replace(antigo_d, f'<meta name="description" content="{d}">\n{extra}', 1)
            .replace(h1, h1.replace("Nível do rio em tempo real", html.escape(f"Nível do {cfg['rio']} em {cfg['cidade']} em tempo real")), 1))


def sitemap():
    """public/sitemap.xml: página inicial, painel de cada rio visível e as páginas de texto."""
    hoje = date.today().isoformat()
    paginas = [("", "1.0"), *((f"{b['id']}/", "0.9") for b in bacias() if not b.get("oculta")),
               ("privacidade.html", "0.2"), ("termos.html", "0.2")]
    linhas = [f"  <url><loc>{SITE}{p}</loc><lastmod>{hoje}</lastmod><changefreq>{'yearly' if p.endswith('.html') else 'hourly'}</changefreq><priority>{pr}</priority></url>"
              for p, pr in paginas]
    (PUBLIC / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                       + "\n".join(linhas) + "\n</urlset>\n", encoding="utf-8")


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
    """Atalhos do ícone do app (toque longo): um por bacia, na ordem de bacias.json (sem as ocultas)."""
    arq = PUBLIC / "manifest.webmanifest"
    m = json.loads(arq.read_text(encoding="utf-8"))
    m["shortcuts"] = [{"name": f"{b['rio']} — {b['cidade']}", "short_name": b["rio"].replace("Rio ", ""), "url": f"./{b['id']}/",
                       "icons": [{"src": "icones/icone-192.png", "sizes": "192x192", "type": "image/png"}]} for b in bacias() if not b.get("oculta")]
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
        (pasta / "index.html").write_text(painel_com_seo((MODELOS / "painel.html").read_text(encoding="utf-8"), b, cfg), encoding="utf-8")
        shutil.copyfile(MODELOS / "tv.html", pasta / "tv.html")
        m = dict(manifesto, name=f"{cfg['rio']} — {cfg['cidade']}", short_name=cfg["rio"],
                 description=f"Nível, chuva e avisos de cheia do {cfg['rio']} em {cfg['cidade']}.")
        (pasta / "manifest.webmanifest").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{b['id']}: painel, modo TV e manifesto prontos")
    atalhos_do_app()
    sitemap()
    if problemas:
        sys.exit(f"{problemas} problema(s) nas configurações")


if __name__ == "__main__":
    main()
