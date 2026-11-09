"""Confere o robô de avisos (scripts/alertas.py) com uma cheia simulada, sem internet e sem mandar nada.

Para cada bacia com cotas de atenção e alerta, faz o rio subir, baixar e ficar sem dados, e confere se sai
exatamente um aviso por mudança (sem repetir), se a descida respeita a folga de 5 cm, se um aviso que não
chegou é tentado de novo e se a régua parada avisa "sem dados" e depois "voltou a transmitir".

Uso: python scripts/testar_alertas.py   (para com erro se algo sair diferente do esperado)
"""
import os, sys, tempfile, types
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.pop("TESTE", None)
import alertas, comum  # noqa: E402

relogio = [datetime.now(timezone.utc).timestamp()]
niveis = {}          # {codigo: cm}; None = régua sem resposta
enviados = []        # textos que o robô mandou nesta rodada
chega = [True]       # False = todos os canais falham


def serie(cod):
    """14 h de leituras paradas no nível atual (sem subida: não dispara os avisos de rio acima)."""
    v = niveis.get(cod)
    if v is None: return []
    fim = datetime.fromtimestamp(relogio[0], timezone.utc)
    return [(fim - timedelta(minutes=10 * k), float(v)) for k in range(84, -1, -1)]


alertas.time = types.SimpleNamespace(time=lambda: relogio[0], sleep=lambda s: None)
alertas.leituras_sibh = lambda ests, horas=14: {e["codigo"]: serie(e["codigo"]) for e in ests}
alertas.leituras_ana = lambda codigo, horas=14: serie(codigo)
alertas.chuva_pluviometro = lambda est: None
alertas.probabilidade = lambda *a, **k: None      # a previsão tem teste próprio (testar_previsao.py)


def mandar(cfg, texto):
    enviados.append(texto)
    return chega[0]


def rodada(bacia, P, nivel, minutos=10):
    relogio[0] += minutos * 60
    niveis[P] = nivel
    enviados.clear()
    falhas = alertas.verificar(bacia, mandar)
    return [t[:1] for t in enviados], falhas


erros = testadas = 0
for bacia in comum.bacias():
    cfg = comum.config(bacia); EST = comum.estacoes(cfg); P = cfg["principal"]
    cotas = EST[P].get("cotas_cm", {})
    if not {"atencao", "alerta"} <= cotas.keys():
        print(f"{bacia}: sem cotas de atenção e alerta, não entra no teste"); continue
    at, al = cotas["atencao"], cotas["alerta"]
    if al - at < 20:
        print(f"{bacia}: cotas muito próximas para este teste"); continue
    testadas += 1
    alertas.PASTA_ESTADO = Path(tempfile.mkdtemp(prefix="alertas-teste-"))
    niveis.clear(); niveis.update({c: 10 for c in EST}); chega[0] = True

    # (o que acontece, nível da régua principal, minutos desde a rodada anterior, avisos esperados, canais funcionam?)
    passos = [
        ("rio normal",                         at - 50, 10, [],     True),
        ("passa da atenção",                   at + 5,  10, ["🔴"], True),
        ("continua em atenção: não repete",    at + 10, 10, [],     True),
        ("passa do alerta",                    al + 5,  10, ["🔴"], True),
        ("3 cm abaixo do alerta: folga",       al - 3,  10, [],     True),
        ("baixa para atenção",                 al - 8,  10, ["🟠"], True),
        ("3 cm abaixo da atenção: folga",      at - 3,  10, [],     True),
        ("abaixo da atenção",                  at - 20, 10, ["🟢"], True),
        ("sobe de novo, canais fora do ar",    at + 5,  10, ["🔴"], False),
        ("canais voltam: tenta de novo",       at + 5,  10, ["🔴"], True),
        ("já avisado: não repete",             at + 6,  10, [],     True),
        ("régua para (1ª rodada sem dados)",   None,   300, [],     True),
        ("régua parada (2ª rodada): avisa",    None,    10, ["⚠"],  True),
        ("régua parada: não repete",           None,    10, [],     True),
        ("régua volta",                        at + 6,  10, ["✅"], True),
    ]
    for oque, nivel, minutos, esperado, funciona in passos:
        chega[0] = funciona
        try:
            saiu, falhas = rodada(bacia, P, nivel, minutos)
        except Exception as e:
            print(f"ERRO {bacia}: {oque}: o robô quebrou ({e!r})"); erros += 1; break
        certo = saiu == esperado and (falhas > 0) == (not funciona and bool(esperado))
        if not certo:
            erros += 1
            print(f"ERRO {bacia}: {oque}: esperava {esperado or 'nenhum aviso'}, saiu {saiu or 'nenhum aviso'} ({falhas} falha(s))")
            for t in enviados: print("     ", t.replace("\n", " | "))
    else:
        print(f"{bacia}: {len(passos)} rodadas simuladas, avisos como esperado")

if not testadas:
    sys.exit("nenhuma bacia com cotas para testar")
if erros:
    sys.exit(f"{erros} diferença(s) no robô de avisos")
print("robô de avisos: ok")
