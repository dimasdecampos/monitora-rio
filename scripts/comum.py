"""Funções usadas por vários scripts: lista de bacias, configuração e consulta à ANA."""
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLIC = RAIZ / "public"
URL_ANA = (
    "http://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"
    "?codEstacao={cod}&dataInicio={ini}&dataFim={fim}"
)


def bacias():
    """Ids das bacias, na ordem de public/bacias.json (ex.: ["paraitinga", "paraibuna"])."""
    return [b["id"] for b in json.loads((PUBLIC / "bacias.json").read_text(encoding="utf-8"))["bacias"]]


def pasta(bacia):
    return PUBLIC / bacia


def config(bacia):
    return json.loads((pasta(bacia) / "config.json").read_text(encoding="utf-8"))


def estacoes(cfg):
    """{codigo: estação} de uma configuração, com o nome do grupo em "grupo"."""
    return {e["codigo"]: dict(e, grupo=r["nome"]) for r in cfg["rios"] for e in r["estacoes"]}


def pluviometros(cfg):
    """{codigo: pluviômetro} — estações só de chuva (sem régua), usadas nas regiões de chuva."""
    return {e["codigo"]: dict(e, grupo="Pluviômetros", so_chuva=True) for e in cfg.get("pluviometros", [])}


def _numero(texto):
    try:
        return float(texto) if texto and texto.strip() else None
    except ValueError:
        return None


def buscar_ana(codigo, inicio, fim):
    """Leituras de uma estação da ANA entre as datas (inclusive), em ordem cronológica.

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
