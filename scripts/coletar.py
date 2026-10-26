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


def sem_picos_falsos(linhas, salto=100):
    """Remove leituras isoladas absurdas (sobe e desce mais de `salto` cm entre vizinhas).

    Ex.: a régua marca 1,80 m, depois 7,02 m, depois 1,81 m — erro do sensor, não cheia.
    """
    linhas = [l for l in linhas if l[1] is None or l[1] >= 0]  # nível negativo é erro
    pontos = [l for l in linhas if l[1] is not None]
    hora = lambda l: datetime.strptime(l[0], "%Y-%m-%dT%H:%M")
    ruins = set()

    # Sensor travado: salta mais de 3 m em até 2 h e depois volta ao nível de antes (em até 3 dias).
    # Uma cheia de verdade sobe aos poucos (a de fev/2026 em Natividade subiu no máximo 2 m/h).
    i = 1
    while i < len(pontos):
        antes = pontos[i - 1]
        if abs(pontos[i][1] - antes[1]) > 300 and (hora(pontos[i]) - hora(antes)).total_seconds() <= 7200:
            for k in range(i + 1, len(pontos)):
                if (hora(pontos[k]) - hora(pontos[i])).total_seconds() > 72 * 3600:
                    break
                if abs(pontos[k][1] - antes[1]) <= 50 and abs(pontos[k][1] - pontos[k - 1][1]) > 300:
                    ruins.update(p[0] for p in pontos[i:k])
                    i = k
                    break
        i += 1

    for i in range(1, len(pontos) - 1):
        # só vale para leituras próximas; em estações com 2 leituras/dia uma subida grande pode ser real
        if (hora(pontos[i + 1]) - hora(pontos[i - 1])).total_seconds() > 4 * 3600:
            continue
        ant, atual, prox = pontos[i - 1][1], pontos[i][1], pontos[i + 1][1]
        if (atual - ant > salto and atual - prox > salto) or (ant - atual > salto and prox - atual > salto):
            ruins.add(pontos[i][0])
    return [l for l in linhas if l[0] not in ruins]


def gerar_diario(codigo):
    """Resume os arquivos mensais em um arquivo diário (usado pela página de análise)."""
    linhas = []
    for arquivo in sorted((PASTA / codigo).glob("????-??.json")):
        linhas += json.loads(arquivo.read_text(encoding="utf-8"))["dados"]
    linhas = sem_picos_falsos(sorted(linhas))

    dias = {}
    for t, nivel, vazao, chuva in linhas:
        dias.setdefault(t[:10], []).append((nivel, vazao, chuva))

    saida = []
    for dia in sorted(dias):
        niveis = [n for n, _, _ in dias[dia] if n is not None]
        vazoes = [v for _, v, _ in dias[dia] if v is not None and 0 <= v < 9000]  # 9999 = código de "sem dado"
        chuvas = [c for _, _, c in dias[dia] if c is not None]
        if not niveis and not chuvas:
            continue
        r = lambda x, casas=1: None if x is None else round(x, casas)
        saida.append([
            dia,
            r(min(niveis)) if niveis else None,
            r(sum(niveis) / len(niveis)) if niveis else None,
            r(max(niveis)) if niveis else None,
            r(sum(vazoes) / len(vazoes), 2) if vazoes else None,
            r(max(vazoes), 2) if vazoes else None,
            r(sum(chuvas)) if chuvas else None,
            len(niveis),
        ])
    (PASTA / codigo / "diario.json").write_text(
        json.dumps({
            "estacao": codigo,
            "campos": ["dia", "nivel_min", "nivel_med", "nivel_max", "vazao_med", "vazao_max", "chuva", "leituras"],
            "dados": saida,
        }, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{codigo}: resumo diário com {len(saida)} dias")


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

    for codigo in codigos:
        gerar_diario(codigo)

    indice = {
        pasta.name: sorted(f.stem for f in pasta.glob("????-??.json"))
        for pasta in sorted(PASTA.iterdir()) if pasta.is_dir()
    }
    (PASTA / "index.json").write_text(
        json.dumps({"atualizado_em": HOJE.isoformat(), "meses": indice}, separators=(",", ":")), encoding="utf-8"
    )
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
