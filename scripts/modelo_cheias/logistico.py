"""Probabilidade de o rio subir pelo menos G cm nas próximas 48 h.

P(subida >= G) = sigmoide(w · x), com x = [1, G, log(1+chuva futura 48h), log(1+chuva 24h), log(1+chuva 72h),
                                     solo (chuva 30 dias), nível atual, interações]
Treino 2015–2021, teste 2022–2026. A chuva "futura" é a que de fato caiu (ERA5): melhor caso,
como se a previsão do tempo fosse perfeita.
"""
import json, math, random, sys
from dados import AQUI, chuva_horaria
t, *_ = chuva_horaria()
fim = t.index("2022-01-01T00")
L = json.load(open(AQUI / "linhas.json"))
COTAS = {"atenção": 345, "alerta": 460, "inundação": 510}
GAPS = [25, 50, 75, 100, 150, 200, 250, 300]

def feats(l, G, com_futuro=True):
    f48 = math.log1p(l["f48"]) if com_futuro else 0.0
    p24, p72 = math.log1p(l["p24"]), math.log1p(l["p72"])
    solo = l["api"] / 100
    g = G / 100
    return [1.0, g, f48, p24, p72, solo, l["H0"] / 100, f48 * solo, f48 * g, p24 * g, g * g]

def treinar(rows, com_futuro, epocas=60, lr=0.05, l2=1e-4):
    random.seed(0)
    dados = []
    for l in rows:
        for G in GAPS:
            dados.append((feats(l, G, com_futuro), 1.0 if l["y"] >= G else 0.0))
    # pesa os positivos (raros)
    pos = sum(y for _, y in dados); wpos = (len(dados) - pos) / max(pos, 1) ** 1 * 0 + 1
    w = [0.0] * len(dados[0][0])
    m = [0.0] * len(w); v = [0.0] * len(w)
    passo = 0
    for ep in range(epocas):
        random.shuffle(dados)
        for k in range(0, len(dados), 256):
            lote = dados[k:k + 256]; grad = [0.0] * len(w)
            for x, y in lote:
                z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-max(-30, min(30, z))))
                e = p - y
                for j in range(len(w)): grad[j] += e * x[j]
            passo += 1
            for j in range(len(w)):
                gj = grad[j] / len(lote) + l2 * w[j]
                m[j] = .9 * m[j] + .1 * gj; v[j] = .999 * v[j] + .001 * gj * gj
                w[j] -= lr * (m[j] / (1 - .9 ** passo)) / (math.sqrt(v[j] / (1 - .999 ** passo)) + 1e-8)
    return w

def prob(w, l, G, com_futuro=True):
    z = sum(a * b for a, b in zip(w, feats(l, G, com_futuro)))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))

def auc(ps, ys):
    pares = sorted(zip(ps, ys)); npos = sum(ys); nneg = len(ys) - npos
    soma = 0; rank = 0
    for i, (p, y) in enumerate(pares):
        if y: soma += i + 1
    return (soma - npos * (npos + 1) / 2) / (npos * nneg)

treino = [l for l in L if l["i"] < fim and l["i"] % 6 == 0]
teste = [l for l in L if l["i"] >= fim]
resultado = {}
if __name__ != "__main__":
    resultado = json.load(open(AQUI / "pesos_logistico.json"))
for com_futuro in ((False, True) if __name__ == "__main__" else ()):
    w = treinar(treino, com_futuro)
    nome = "com chuva prevista (perfeita)" if com_futuro else "só chuva que já caiu"
    print(f"\n=== {nome} ===")
    for cota, cm in COTAS.items():
        casos = [l for l in teste if l["H0"] < cm]
        ys = [1 if l["H0"] + l["y"] >= cm else 0 for l in casos]
        ps = [prob(w, l, cm - l["H0"], com_futuro) for l in casos]
        if sum(ys) == 0: continue
        linha = f"  {cota:10s} eventos={sum(ys):4d}/{len(ys)}  AUC={auc(ps, ys):.3f}"
        for lim in (0.2, 0.35, 0.5):
            al = [y for p, y in zip(ps, ys) if p >= lim]
            pod = sum(al) / sum(ys); far = 1 - sum(al) / len(al) if al else 0
            linha += f" | p≥{lim:.2f}: acerta {pod*100:4.0f}% falsos {far*100:4.0f}%"
        print(linha)
        # confiabilidade: quando o modelo diz X%, acontece quanto?
        if cota == "atenção":
            print("    confiabilidade (previsto → observado):", end="")
            for a, b in ((0, .1), (.1, .3), (.3, .5), (.5, .7), (.7, 1.01)):
                g = [(p, y) for p, y in zip(ps, ys) if a <= p < b]
                if g: print(f"  {a*100:.0f}–{min(b,1)*100:.0f}%: {sum(y for _, y in g)/len(g)*100:.0f}% (n={len(g)})", end="")
            print()
    resultado["futuro" if com_futuro else "passado"] = w
if __name__ == "__main__": json.dump(resultado, open(AQUI / "pesos_logistico.json", "w"))
print("\npesos:", {k: [round(x, 3) for x in v] for k, v in resultado.items()})
