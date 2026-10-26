"""Função serverless (Vercel): leituras recentes de uma estação da ANA.

GET /api/dados?estacao=58040000&dias=3   (dias: 1 a 45)

O histórico mais antigo fica em public/historico (gerado por scripts/coletar.py).
A resposta fica 5 min no cache da Vercel, então a ANA é consultada no máximo
uma vez a cada 5 min por URL, não importa quantas pessoas abram a página.
"""

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

URL_ANA = (
    "http://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"
    "?codEstacao={cod}&dataInicio={ini}&dataFim={fim}"
)
FUSO_BRASILIA = timezone(timedelta(hours=-3))
MAX_DIAS = 45


def _carregar_estacoes():
    for caminho in (
        Path(__file__).resolve().parent.parent / "public" / "config.json",
        Path.cwd() / "public" / "config.json",
    ):
        if caminho.exists():
            config = json.loads(caminho.read_text(encoding="utf-8"))
            return {e["codigo"] for rio in config["rios"] for e in rio["estacoes"]}
    return None  # sem config: aceita qualquer código de 8 dígitos


ESTACOES = _carregar_estacoes()


def _numero(texto):
    try:
        return float(texto) if texto and texto.strip() else None
    except ValueError:
        return None


def buscar_ana(codigo, inicio, fim):
    """Leituras da estação entre as datas (inclusive), em ordem cronológica.

    Cada leitura: {"t": "AAAA-MM-DDTHH:MM:SS", "nivel": cm, "vazao": m³/s, "chuva": mm}
    """
    url = URL_ANA.format(cod=codigo, ini=inicio.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
    with urllib.request.urlopen(url, timeout=60) as resp:
        raiz = ET.fromstring(resp.read())

    leituras = {}
    for item in raiz.iter():
        if not item.tag.endswith("DadosHidrometereologicos"):
            continue
        campos = {filho.tag.split("}")[-1]: filho.text for filho in item}
        data = (campos.get("DataHora") or "").strip()
        if not data:
            continue
        leituras[data] = {
            "t": data.replace(" ", "T"),
            "nivel": _numero(campos.get("Nivel")),
            "vazao": _numero(campos.get("Vazao")),
            "chuva": _numero(campos.get("Chuva")),
        }
    return [leituras[k] for k in sorted(leituras)]


def dados_recentes(codigo, dias):
    hoje = datetime.now(FUSO_BRASILIA).date()
    return {
        "estacao": codigo,
        "consultado_em": datetime.now(FUSO_BRASILIA).isoformat(timespec="seconds"),
        "leituras": buscar_ana(codigo, hoje - timedelta(days=dias), hoje + timedelta(days=1)),
    }


def responder(qs):
    """Retorna (status, corpo, segundos_de_cache) para os parâmetros da URL."""
    codigo = (qs.get("estacao") or [""])[0]
    if not re.fullmatch(r"\d{8}", codigo) or (ESTACOES and codigo not in ESTACOES):
        return 400, {"erro": "Estação desconhecida"}, 0
    try:
        dias = max(1, min(int((qs.get("dias") or ["3"])[0]), MAX_DIAS))
    except ValueError:
        dias = 3
    try:
        return 200, dados_recentes(codigo, dias), 300
    except Exception as erro:  # ANA fora do ar, rede etc.
        return 502, {"erro": f"Falha ao consultar a ANA: {erro}"}, 0


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, corpo, cache = responder(parse_qs(urlparse(self.path).query))
        dados = json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Cache-Control",
            f"public, s-maxage={cache}, stale-while-revalidate=600" if cache else "no-store",
        )
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)
