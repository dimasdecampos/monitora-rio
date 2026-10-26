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

## O que alaga e memória das cheias

`public/impactos.json` liga níveis da Passarela a impactos registrados (2021, 2022,
2024), com os lugares no mapa (coordenadas do OpenStreetMap) e a linha do tempo das
grandes cheias desde 1863 (relatório SGB/CPRM 2022 e notícias). Os níveis das ruas do
centro são aproximados; edite o arquivo para corrigir ou acrescentar registros.

## Previsão na Passarela

`scripts/modelo_cheias/passarela.py` e `exportar_passarela.py` treinam a previsão
direto na régua da Passarela (2018–2026), com a subida da régua de Cunha quando ela
está transmitindo. Teste com a previsão do tempo real (2024–2026, 8 vezes acima da
atenção): avisou 7 com 6 h de antecedência; com Cunha, os dias de alarme falso
caíram de 44% para 35%. A linha de previsão do gráfico erra em média 15 cm em 2 dias.

## Avisos

- **No aparelho**: botão "Avisar neste aparelho" (funciona com o painel aberto ou
  instalado como app).
- **Telegram** (funciona sempre): `scripts/alertas.py` roda a cada ~10 min pelo
  `.github/workflows/alertas.yml`. Para ligar:
  1. No Telegram, fale com **@BotFather**, crie um bot (`/newbot`) e copie o token.
  2. Crie um canal público, adicione o bot como administrador.
  3. No GitHub: *Settings → Secrets and variables → Actions* → crie
     `TELEGRAM_TOKEN` (o token) e `TELEGRAM_CHAT` (`@nome_do_canal`).
  4. Em `public/config.json`, preencha `"telegram": "https://t.me/nome_do_canal"`
     para o painel mostrar o botão do canal.
  Sem os segredos, o robô roda em modo de teste e só registra as mensagens.

## App instalável

`public/manifest.webmanifest` e `public/sw.js` deixam o painel instalável no celular
("Adicionar à tela inicial"); sem internet, ele mostra a última leitura guardada.

## Definição das cotas (auditoria de 26/10/2026)

Segundo o *Manual de Operação das Salas de Situação do Estado de São Paulo*
(ANA/ProGestão), as cotas da SP Águas significam:

| Cota | Significado oficial |
|---|---|
| abaixo da atenção | normal |
| Atenção | risco significativo de evento adverso, mas ainda incerto |
| Alerta | perigo iminente ou previsível a curto prazo; Defesa Civil de prontidão |
| Emergência | situação crítica que demanda ação imediata |
| Extravasamento | rio acima das margens, transbordando (no painel: "Transbordamento") |

Cotas usadas: Passarela e demais réguas da SP Águas = cadastradas no SIBH. Régua da
ANA na cidade = atenção 2,73 m e alerta 3,16 m cadastradas no SIBH para ela;
emergência e transbordamento convertidos da Passarela (ANA ≈ 123 + 1,017 × Passarela,
conferido de novo em 26/10/2026: diferença de 2–5 cm). As duas tabelas oficiais não
batem entre si: a atenção da régua da ANA equivale a ~1,48 m na Passarela (lá é 1,92 m).

Filtros de qualidade: saltos impossíveis, sensor travado (mesmo valor por horas depois
de um salto > 2 m, ex. 10,31 m no Ribeirão do Chapéu em jul/2024) e chuvas impossíveis
(contador acumulado da Passarela de dez/2021 a out/2023) são descartados.
