"""Baixa o histórico das estações da ANA e salva em public/historico/.

Formato: public/historico/<codigo>/<AAAA-MM>.json  (um arquivo por mês)
         public/historico/index.json               (meses disponíveis por estação)

Uso:
  python scripts/coletar.py                 # atualiza o mês atual e o anterior (roda todo dia no GitHub)
  python scripts/coletar.py --desde 2024-01 # baixa tudo desde jan/2024 (carga inicial)
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from api.dados import buscar_ana  # noqa: E402

PASTA = RAIZ / "public" / "historico"
HOJE = datetime.now(timezone(timedelta(hours=-3))).date()


def meses(desde):
    atual = desde.replace(day=1)
    while atual <= HOJE:
        yield atual
        atual = (atual + timedelta(days=32)).replace(day=1)


def ultimo_dia(mes):
    return (mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def baixar_mes(codigo, mes, tentativas=3):
    for n in range(tentativas):
        try:
            leituras = buscar_ana(codigo, mes, ultimo_dia(mes))
            prefixo = mes.strftime("%Y-%m")
            return [
                [l["t"][:16], l["nivel"], l["vazao"], l["chuva"]]
                for l in leituras
                if l["t"].startswith(prefixo)
            ]
        except Exception as erro:
            print(f"  erro ({erro}), tentativa {n + 1}/{tentativas}")
            time.sleep(5 * (n + 1))
    raise RuntimeError(f"Não foi possível baixar {codigo} {mes:%Y-%m}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--desde", help="AAAA-MM: primeiro mês a baixar (padrão: mês anterior)")
    args = p.parse_args()
    if args.desde:
        inicio = datetime.strptime(args.desde, "%Y-%m").date()
    else:
        inicio = (HOJE.replace(day=1) - timedelta(days=1)).replace(day=1)

    config = json.loads((RAIZ / "public" / "config.json").read_text(encoding="utf-8"))
    codigos = [e["codigo"] for rio in config["rios"] for e in rio["estacoes"]]
    falhas = 0

    for codigo in codigos:
        pasta = PASTA / codigo
        pasta.mkdir(parents=True, exist_ok=True)
        for mes in meses(inicio):
            try:
                linhas = baixar_mes(codigo, mes)
            except RuntimeError as erro:
                print(erro)
                falhas += 1
                continue
            arquivo = pasta / f"{mes:%Y-%m}.json"
            if not linhas:
                print(f"{codigo} {mes:%Y-%m}: sem leituras")
                continue
            antigo = json.loads(arquivo.read_text(encoding="utf-8"))["dados"] if arquivo.exists() else []
            if len(linhas) < len(antigo):
                # a ANA às vezes responde incompleto; nunca troca dados bons por menos dados
                print(f"{codigo} {mes:%Y-%m}: resposta menor que a salva ({len(linhas)} < {len(antigo)}), mantendo")
                continue
            conteudo = json.dumps(
                {"estacao": codigo, "mes": f"{mes:%Y-%m}", "campos": ["t", "nivel", "vazao", "chuva"], "dados": linhas},
                ensure_ascii=False, separators=(",", ":"),
            )
            if not arquivo.exists() or arquivo.read_text(encoding="utf-8") != conteudo:
                arquivo.write_text(conteudo, encoding="utf-8")
                print(f"{codigo} {mes:%Y-%m}: {len(linhas)} leituras salvas")

    indice = {
        pasta.name: sorted(f.stem for f in pasta.glob("*.json"))
        for pasta in sorted(PASTA.iterdir()) if pasta.is_dir()
    }
    (PASTA / "index.json").write_text(
        json.dumps({"atualizado_em": HOJE.isoformat(), "meses": indice}, separators=(",", ":")), encoding="utf-8"
    )
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
