# Monitor dos rios Paraitinga e Paraibuna

Nível, vazão e chuva em tempo real do Rio Paraitinga (São Luiz do Paraitinga) e do
Rio Paraibuna (Fazenda Palmeiras, Natividade da Serra), com dados da rede
telemétrica da ANA.

## Como funciona

O site é publicado no GitHub Pages. A página busca as leituras recentes direto
na ANA, pelo navegador, e lê o histórico salvo neste repositório.

| Parte | O que faz |
|---|---|
| `public/index.html` | Painel principal: agora, últimos dias com chuva, comparação entre anos e histórico (pensado para celular) |
| `public/classico.html` | Versão anterior da página de tempo real |
| `public/analise.html` | Versão anterior da página de histórico e comparação |
| `public/historico/<estação>/diario.json` | Resumo diário usado na página de análise (gerado pelo coletor) |
| `public/config.json` | Estações e cotas de atenção/alerta/inundação |
| `public/historico/` | Histórico salvo, um arquivo por estação e mês |
| `scripts/coletar.py` | Baixa o histórico da ANA |
| `.github/workflows/site.yml` | Todo dia às 06:20 salva o histórico novo e publica o site; também publica a cada push |
| `api/dados.py` | Consulta à ANA usada pelo coletor e pelo servidor local (também funciona como função na Vercel, opcional) |

## Rodar no computador

```
python server.py
```

Abre em http://localhost:8000. Não precisa instalar nada além do Python.

## Histórico

O GitHub atualiza o mês atual e o anterior todo dia. Para baixar meses mais antigos:

```
python scripts/coletar.py --desde 2022-01
```

## Cotas

As cotas não são oficiais. No Paraitinga elas foram estimadas com cheias reais
registradas na régua ANA/CPRM 58040000 (5,23 m em 2021, 6,49 m em 2024 e
6,52 m em 2022). Ajuste em `public/config.json`.

## Previsão de cheias (experimental)

O painel mostra a chance de o Paraitinga, em São Luiz, chegar a cada cota nas
próximas 48 h. O cálculo roda no navegador com:

- o nível atual (régua da CESP, 58041000, a mesma usada no treino);
- a chuva média da bacia (São Luiz, Lagoinha, Cunha, cabeceiras) dos últimos
  31 dias e a prevista, do [Open-Meteo](https://open-meteo.com), com 31 cenários
  do GFS para medir a incerteza.

O modelo é uma regressão logística treinada com 2015–2021
(`scripts/modelo_cheias/`, veja a ordem de execução em `exportar.py`) e
exportada para `public/modelo_cheias.json`.

Teste com a previsão do tempo real (fev/2024 a out/2026, 15 vezes em que o rio
passou da cota de atenção): avisou 9 com 6 h de antecedência, 4 com 12 h e 2
com 24 h; em 12 dos 30 dias com aviso a cheia não veio. Sem a previsão de
chuva, seriam 6 avisadas com 6 h. Tempestades localizadas na serra ainda escapam.
Não substitui os alertas da Defesa Civil.
