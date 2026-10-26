# Monitor dos rios Paraitinga e Paraibuna

Nível, vazão e chuva em tempo real do Rio Paraitinga (São Luiz do Paraitinga) e do
Rio Paraibuna (Fazenda Palmeiras, Natividade da Serra), com dados da rede
telemétrica da ANA.

## Como funciona

O site é publicado no GitHub Pages. A página busca as leituras recentes direto
na ANA, pelo navegador, e lê o histórico salvo neste repositório.

| Parte | O que faz |
|---|---|
| `public/index.html` | Página de tempo real |
| `public/analise.html` | Histórico e comparação entre anos (estação, período do ano, medida) |
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
