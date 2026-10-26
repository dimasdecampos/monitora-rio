# Monitor do Rio Paraitinga — São Luiz do Paraitinga (SP)

Painel em tempo real do nível e da chuva do Rio Paraitinga, de Cunha até São Luiz do
Paraitinga, e do Rio Paraibuna, com previsão experimental de cheias, histórico desde
2015/2018 e avisos.

**Painel:** https://dimasdecampos.github.io/monitora-rio-slp/

> **Idealização e criação: Dimas de Campos.** Desenvolvido em parceria com IA
> (Claude, da Anthropic).

> ⚠️ **Aviso importante.** Este é um projeto independente. **Os dados, cotas,
> impactos e previsões NÃO foram validados pela Defesa Civil** nem por nenhum órgão
> oficial. As informações vêm de fontes públicas e de cálculos próprios, podem conter
> erros, atrasos ou falhas de transmissão. **Qualquer uso é de responsabilidade
> própria.** Em situação de risco, siga sempre as orientações da **Defesa Civil (199)**
> e dos **Bombeiros (193)**.

---

## Sumário

1. [O que o painel mostra](#o-que-o-painel-mostra)
2. [Fontes de dados](#fontes-de-dados)
3. [Cotas e classificação do nível](#cotas-e-classificação-do-nível)
4. [Réguas da cidade: conversão e preenchimento](#réguas-da-cidade-conversão-e-preenchimento)
5. [Qualidade dos dados (filtros)](#qualidade-dos-dados-filtros)
6. [Previsão de cheias (experimental)](#previsão-de-cheias-experimental)
7. [Rio acima e chuva na bacia](#rio-acima-e-chuva-na-bacia)
8. [O que alaga, memória e estatísticas](#o-que-alaga-memória-e-estatísticas)
9. [Avisos](#avisos)
10. [Atualização automática](#atualização-automática)
11. [Estrutura do projeto](#estrutura-do-projeto)
12. [Rodar e atualizar](#rodar-e-atualizar)
13. [Limitações conhecidas](#limitações-conhecidas)
14. [Créditos](#créditos)

---

## O que o painel mostra

Uma única página, pensada primeiro para o celular:

| Parte | O que mostra |
|---|---|
| Nível agora | Última leitura da régua escolhida, situação (normal, atenção, alerta, emergência, transbordamento), tendência em cm/h e comparação com o normal da época |
| Números rápidos | Chuva 24 h e 7 dias, vazão, pico do ano, dias acima da atenção |
| Gráfico "Últimos dias" | Nível medido + linha de previsão de 7 dias com faixa de 8 em 10 chances, nível típico da época, chuva medida e prevista (na régua ou na bacia, por região); zoom e rolagem pela barra de navegação |
| Gráfico "Comparar anos" | Um ano por linha no período escolhido (ano, chuvoso, verão, hidrológico), mediana e faixa dos anos completos |
| Rio acima | Réguas de Cunha → Lagoinha → Estrada do Ribeira → cidade, com tempo típico de chegada da água e indicador de represamento pelo Ribeirão do Chapéu |
| Previsão 48 h | Chance de chegar a cada cota oficial, pico provável e chuva prevista por dia |
| O que alaga | Escada de níveis com impactos registrados e mapa do centro |
| Ano a ano, maiores cheias, mapa mensal | Histórico por ano e mês |
| Visões extras (fechadas) | Chuva × subida do rio, quando o rio enche, tempo para baixar, permanência, memória das cheias |
| Situação das fontes | Se cada fonte está transmitindo |

Cartões menos usados começam fechados para economizar espaço; o navegador lembra o que
cada visitante abriu.

## Fontes de dados

| Fonte | O que vem | Frequência | Acesso |
|---|---|---|---|
| [SP Águas — SIBH](https://cth.daee.sp.gov.br/sibh/) | Nível e chuva das réguas da SP Águas (Passarela, Estrada do Ribeira, Lagoinha ×2, Cunha, Rio Jacuí, Ribeirão do Chapéu ×2, Ponte Alta) e cotas oficiais | 10 min | API pública, direto no navegador (máx. 10 estações por chamada) |
| [ANA — telemetria](https://www.snirh.gov.br/hidrotelemetria/) | Réguas da cidade (58040000), CESP (58041000) e Fazenda Palmeiras (58068000) | 15 min | Web service público, direto no navegador |
| [Open-Meteo](https://open-meteo.com) | Chuva prevista (8 dias), 31 cenários GFS, chuva histórica ERA5 e previsões arquivadas | horária | API pública |
| [OpenStreetMap](https://www.openstreetmap.org) | Mapa e coordenadas das ruas | — | Tiles públicos |
| Relatório SGB/CPRM 2022 e notícias | Cheias históricas e impactos | — | Links no painel |

A estação padrão é a **Passarela (SP Águas)**, no centro, que tem cotas oficiais.

## Cotas e classificação do nível

Definição oficial, segundo o *Manual de Operação das Salas de Situação do Estado de
São Paulo* (ANA/ProGestão):

| Situação | Significado oficial | Cor |
|---|---|---|
| Normal | Abaixo da cota de atenção | verde |
| Atenção | Risco significativo de evento adverso, mas ainda incerto | amarelo |
| Alerta | Perigo iminente ou previsível a curto prazo; Defesa Civil de prontidão | laranja |
| Emergência | Situação crítica que demanda ação imediata | vermelho |
| Transbordamento (*extravasamento*) | Rio acima das margens, transbordando | vermelho escuro |

Cotas usadas (em metros, na régua de cada estação):

| Estação | Atenção | Alerta | Emergência | Transb. | Origem |
|---|---|---|---|---|---|
| Passarela (SP Águas) | 1,92 | 2,32 | 2,72 | 3,12 | Oficiais (SIBH) |
| Régua da ANA na cidade | 2,73 | 3,16 | 4,00 | 4,41 | Atenção e alerta oficiais (SIBH); emergência e transbordamento convertidos da Passarela |
| Régua da CESP | 3,04 | 3,48 | 3,91 | 4,35 | Convertidas da Passarela (aproximadas) |
| Lagoinha, Cunha, Rio Jacuí, Chapéu, Ponte Alta | — | — | — | — | Oficiais (SIBH), ver `public/config.json` |
| Fazenda Palmeiras (ANA) | 2,50 | 3,50 | 4,50 | — | Provisórias, pelo histórico |

As duas tabelas oficiais da cidade não batem entre si: a atenção da régua da ANA
(2,73 m) equivale a ~1,48 m na Passarela, cuja atenção oficial é 1,92 m. **Confirme com a
Defesa Civil qual tabela é usada nas sirenes.**

Outras regras de classificação:

- **Tendência:** variação na última hora — subindo (≥ 2 cm/h), subindo rápido (≥ 10 cm/h),
  baixando (≤ −2 cm/h), estável.
- **Leitura atrasada:** acima de 1 h (SP Águas) ou 2 h (ANA) sem leitura nova, o painel
  avisa e sugere trocar para outra régua da cidade.
- **"Acima do normal":** comparação com a mediana do nível médio diário nos mesmos
  ±7 dias do ano, nos anos anteriores.

## Réguas da cidade: conversão e preenchimento

As réguas da Passarela, da ANA e da CESP medem o mesmo trecho do rio com zeros diferentes:

- **ANA ≈ 123,4 + 1,017 × Passarela** (cm), erro típico de 3 a 7 cm (conferido em 2026).
- **CESP ≈ 95 + 1,09 × Passarela** (cm), com dados de 2026 (antes disso a relação varia).

Quando uma régua da cidade fica sem transmitir, **os dias que faltam no histórico são
completados com a outra convertida** (Passarela ⇄ ANA) e marcados como "completados".
Exemplo: a Passarela parou de 10/09 a 15/09/2026 e o preenchimento revelou uma cheia
(~2,55 m em 12/09). O gráfico de "Últimos dias" (ao vivo) não é preenchido.

## Qualidade dos dados (filtros)

Descartados automaticamente (coletor, painel ao vivo e robô de avisos):

- nível negativo;
- leitura isolada que sobe e desce mais de 1 m entre vizinhas próximas;
- salto de mais de 3 m em até 2 h que volta ao nível anterior (sensor travado);
- **valor fixo repetido por 6+ leituras logo depois de um salto de mais de 2 m** (régua
  voltando de falha, ex.: 10,31 m no Ribeirão do Chapéu em jul/2024);
- ao vivo: salto de mais de 3 m em até 6 h;
- chuva negativa, mais de 50 mm em 10 min ou mais de 150 mm/h (inclui o contador
  acumulado do pluviômetro da Passarela de dez/2021 a out/2023);
- vazão 9999 (código de "sem dado" da ANA).

Anos com falhas aparecem como **parciais** e podem subestimar picos.

## Previsão de cheias (experimental)

**Chance de chegar a cada cota em 48 h** — regressão logística na régua da Passarela
(`scripts/modelo_cheias/passarela.py`, `exportar_passarela.py`):

- entradas: nível atual, chuva média na bacia (São Luiz, Lagoinha, Cunha, cabeceiras) nas
  últimas 24 h e 72 h, chuva dos 30 dias anteriores (solo encharcado), chuva prevista
  para 48 h (média de 31 cenários GFS) e, quando transmite, a subida da régua de Cunha;
- treino 2018–2023; teste fev/2024–out/2026 com a previsão do tempo **real** da época:
  das 8 vezes em que a Passarela passou da atenção, avisou (chance ≥ 30%) 7 com 6 h de
  antecedência; 44% dos dias com aviso não tiveram cheia (35% com a régua de Cunha);
- o aviso costuma vir **6 a 12 h antes**; tempestades localizadas na serra podem escapar.

**Linha de previsão (7 dias)** — uma regressão por prazo (6 h a 7 dias) para a variação
do nível; a faixa azul é o intervalo de 8 em 10 chances, tirado dos erros do próprio
modelo. Erro médio com previsão real: 10 cm em 1 dia, 15 cm em 2 dias, 21 cm em 7 dias
("fica como está": 13, 20 e 29 cm). A faixa acertou 81–87% das vezes. Não acerta bem o
tamanho de subidas grandes.

**Depois de 7 dias** o gráfico não prevê: previsão de chuva para semanas ou meses não é
confiável o bastante. O gráfico vai só até o fim da previsão.

## Rio acima e chuva na bacia

Tempo típico até a água chegar à Passarela (correlação das subidas, 2024–2026):
Estrada do Ribeira **3 h**, Lagoinha–Barro Vermelho **9 h**, Lagoinha–Jusante do Jacuí
**11 h**, Cunha **~20 h**. O cartão avisa quando alguma régua sobe ≥ 10 cm em 3 h.

**Represamento pelo Ribeirão do Chapéu** (deságua logo abaixo da cidade; agravou 1996 e
2010): *alto* quando o Chapéu passa da atenção e a Passarela está em alerta; *atenção*
quando o Chapéu passa da atenção ou sobe rápido com a cidade alta.

**Chuva na bacia** (botão no gráfico): barras empilhadas por região — Cunha (Est. de Cunha
e Rio Jacuí), Lagoinha (2 réguas), Perto da cidade (Estrada do Ribeira e Passarela) e
Ribeirão do Chapéu (2 réguas). Cada região é a média dos seus pluviômetros (SP Águas)
e a barra é a **soma das regiões**; no futuro, previsão Open-Meteo nos mesmos pontos.
A legenda (recolhida) lista as regiões da que mais choveu para a que menos; tocar liga
ou desliga a região.

## O que alaga, memória e estatísticas

- `public/impactos.json`: níveis da Passarela ligados a impactos registrados (3,95 m:
  ruas da beira do rio, 2021; ~4,60 m: ruas do centro, 2024 — aproximado; 5,36 m: Praça
  da Matriz, 2022), pontos no mapa e linha do tempo das cheias desde 1863.
- `public/estatisticas.json` (gerado por `scripts/estatisticas.py`): frequência de cheias
  por mês, tempo para baixar depois do pico, e chuva × subida do rio por umidade do solo.

## Avisos

- **No aparelho:** botão "Avisar neste aparelho" (Notification API); funciona com o painel
  aberto ou instalado como app. Depois de ligado, o cartão some; para desligar, use o
  rodapé.
- **Telegram:** `scripts/alertas.py` roda a cada ~10 min (`.github/workflows/alertas.yml`).
  Avisa quando a Passarela muda de cota, a água sobe ≥ 20 cm em 3 h rio acima (com tempo
  de chegada), há risco de represamento ou a previsão passa de 30%. Cada tipo de aviso se
  repete no máximo a cada 6–12 h. Para ligar:
  1. No Telegram, crie um bot com **@BotFather** (`/newbot`) e copie o token.
  2. Crie um canal público e adicione o bot como administrador.
  3. No GitHub: *Settings → Secrets and variables → Actions* → `TELEGRAM_TOKEN` e
     `TELEGRAM_CHAT` (`@nome_do_canal`).
  4. Em `public/config.json`, preencha `"telegram": "https://t.me/nome_do_canal"`.

  Sem os segredos, o robô roda em modo de teste e só registra as mensagens.
- **App ntfy (recomendado):** notificação no celular com som de alarme, grátis e sem
  cadastro. Instale o app **ntfy** (Android/iPhone), toque em **+** e assine o tópico
  guardado no segredo `NTFY_TOPIC` (nome difícil de adivinhar, pois quem souber o nome
  recebe os avisos). Para várias pessoas, todas assinam o mesmo tópico.
- **WhatsApp (pessoal, via [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)):**
  os mesmos avisos chegam no seu WhatsApp, de graça. Funciona só para números
  individuais (não para grupos), e cada número precisa ativar o próprio acesso.
  1. Salve o número do CallMeBot indicado no site deles e mande a mensagem de ativação
     que aparece lá. A resposta traz sua `apikey`.
  2. No GitHub: *Settings → Secrets and variables → Actions* → `CALLMEBOT_PHONE`
     (ex.: `+5512999999999`) e `CALLMEBOT_KEY`.
  3. Teste: *Actions → Avisos de cheia → Run workflow*, marque **teste** e rode. Chega
     uma mensagem com o nível atual.
- **App instalável:** `public/manifest.webmanifest` e `public/sw.js` (funciona sem internet
  com a última leitura guardada).

## Atualização automática

| Workflow | Quando | O que faz |
|---|---|---|
| `site.yml` | todo dia às 06:20 e a cada push | baixa o mês atual e o anterior (ANA e SP Águas), gera os resumos diários (com preenchimento), atualiza as estatísticas e publica o site no GitHub Pages |
| `alertas.yml` | a cada ~10 min | verifica o rio e envia os avisos do Telegram e do WhatsApp |

O GitHub pode atrasar tarefas agendadas em alguns minutos.

## Estrutura do projeto

```
public/                    site publicado no GitHub Pages
  index.html               painel (HTML + CSS + JS, sem build)
  config.json              estações, cotas, conversões, regiões de chuva
  modelo_cheias.json       pesos dos modelos de previsão e resultados dos testes
  impactos.json            o que alaga, lugares no mapa, memória das cheias
  estatisticas.json        sazonalidade, recessão, chuva × subida
  historico/<estação>/     AAAA-MM.json (leituras) e diario.json (resumo diário)
  manifest.webmanifest, sw.js, icones/   app instalável
scripts/
  coletar.py               coleta ANA + SP Águas, filtros, resumo diário e preenchimento
  estatisticas.py          gera estatisticas.json
  alertas.py               robô de avisos do Telegram
  modelo_cheias/           download de chuva (ERA5, previsões arquivadas), treino e testes
api/dados.py               consulta à ANA (servidor local / Vercel, opcional)
server.py                  servidor local para testes
```

## Rodar e atualizar

```bash
python server.py                                  # painel em http://localhost:8000
python scripts/coletar.py                         # atualiza o mês atual e o anterior
python scripts/coletar.py --desde 2018-01 --estacao sp664   # recarrega uma estação
python scripts/estatisticas.py                    # recalcula as estatísticas
```

Para refazer os modelos, siga a ordem descrita em `scripts/modelo_cheias/exportar.py`
e depois rode `exportar_passarela.py`. Só usa a biblioteca padrão do Python.

## Limitações conhecidas

- Cotas, impactos e previsões **não validados pela Defesa Civil**.
- Previsão testada com poucas cheias recentes (8); aviso de poucas horas.
- Níveis das ruas do centro em 2024 são aproximados; faltam pontos de referência oficiais.
- Lagoinha (Jusante do Jacuí) e Estrada do Ribeira têm menos de 1 ano de histórico.
- Cotas oficiais de Ponte Alta (a partir de 5,20 m) nunca foram atingidas desde 2024.
- Fontes podem parar de transmitir (ex.: ANA em 26/10/2026, Passarela em set/2026).
- Horários são exibidos no fuso do aparelho (o painel assume horário de Brasília).

## Créditos

- **Idealização, criação e coordenação: Dimas de Campos.**
- Desenvolvimento em parceria com IA: **Claude (Anthropic)**.
- Dados: SP Águas (SIBH), ANA, Open-Meteo, OpenStreetMap; histórico de cheias do
  relatório SGB/CPRM (2022) e imprensa regional.

**Os dados não foram validados pela Defesa Civil. Qualquer uso é de responsabilidade
própria.**
