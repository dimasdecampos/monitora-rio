# Monitor dos rios Paraitinga e Paraibuna

Nível e chuva em tempo real do Rio Paraitinga (de Cunha a São Luiz do
Paraitinga) e do Rio Paraibuna, com dados da rede telemétrica da
[SP Águas (SIBH)](https://cth.daee.sp.gov.br/sibh/) e da ANA.

## Fontes de dados

| Fonte | Estações | Observação |
|---|---|---|
| SP Águas (SIBH) | Passarela (centro, padrão), Estrada do Ribeira, Lagoinha (2), Cunha, Rio Jacuí, Ribeirão do Chapéu (2), Ponte Alta | Leituras a cada 10 min, cotas oficiais (atenção, alerta, emergência, extravasamento). API aberta, no máx. 10 estações por chamada. |
| ANA | Régua da cidade (58040000), CESP (58041000), Fazenda Palmeiras (58068000) | Leituras a cada 15 min; histórico desde 2015. |

Conversões entre as réguas da cidade (em `public/config.json`): ANA = 123 + 1,017 × Passarela
(erro típico 7 cm); CESP ≈ 95 + 1,09 × Passarela (dados de 2026).

Tempo típico para a água chegar à Passarela (correlação das subidas, 2024–2026):
Estrada do Ribeira 3 h, Lagoinha–Barro Vermelho 9 h, Lagoinha–Jusante do Jacuí 11 h, Cunha ~20 h.

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

Nas réguas da SP Águas são as cotas oficiais cadastradas no SIBH. Na Passarela:
atenção 1,92 m, alerta 2,32 m, emergência 2,72 m e extravasamento 3,12 m. Nas
réguas da ANA e da CESP são as mesmas cotas convertidas. Em Natividade da Serra
são provisórias. Ajuste em `public/config.json`.

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

### Linha de previsão no gráfico

Na visão "Últimos dias", o gráfico continua para o futuro:

- **7 dias de previsão**: uma regressão por prazo (6 h a 7 dias,
  `scripts/modelo_cheias/trajetoria.py`) estima a mudança de nível a partir da
  chuva prevista; a faixa azul mostra 8 em 10 chances, tirada dos erros do
  próprio modelo. Testada com previsões reais de 2024–2026: erro médio de 18 cm
  em 2 dias e 26 cm em 7 dias (contra 24 e 35 cm de "o rio fica como está"); a
  faixa acertou 74–84% das vezes. Ela não acerta bem o tamanho de subidas
  grandes — para isso, veja a chance de cheia no cartão de previsão.
- **Até 30 dias**: só a faixa típica do nível para a época (anos anteriores).
  Previsão de chuva para meses não é confiável o bastante para prever o rio.
