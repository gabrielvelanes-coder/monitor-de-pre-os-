# Monitor de Preço de Mercado

Painel Django para **monitorar** (não recomendar) preço nosso x concorrência,
usando os dados que o [robo_cotacao](../../robo_cotacao) já capta todo dia no
Preço da Hora — e, numa 2ª tela ainda não construída, sinalizar variações de
preço de entrada (compra) que merecem olhar.

Projeto separado, git próprio (não reaproveita código do robo_cotacao nem dos
outros painéis — só dados e regras de negócio já validadas).

## Como rodar

```
.venv\Scripts\python manage.py runserver
```

Login do admin (`/admin/`): `velanes` / `velanes`.

## Arquitetura

- **`apps/lojas`** — cadastro de lojas (nome/bandeira/cidade/bairro/zona),
  importado de `lojas_config.json` (mesmo arquivo do robo_cotacao — fonte
  única, sem cadastro duplicado). `manage.py importar_lojas`.
- **`apps/captacao`** — espelho da tabela `precos` do
  `_precos_continuos.sqlite3` do robô. `manage.py sincronizar_captacao` lê de
  lá (somente leitura, nunca escreve no banco do robô) e faz upsert aqui.
  `Rede` classifica cada `estabelecimento` bruto em "nossa bandeira" ou
  "concorrente" (seed inicial de `concorrentes_config.json`, editável no
  admin dali pra frente). `manage.py seed_redes`.
- **`apps/monitor`** — a tela "Monitor de Preço": por EAN, nosso preço médio
  (por bandeira/cidade) x menor preço da concorrência na mesma cidade,
  diferença %. Sem motor de sugestão de preço — só monitoramento e
  comparação (pedido explícito do Gabriel).
- **`apps/produtos`** — cadastro `Produto`, cruzando 2 relatórios do ERP que
  não compartilham EAN entre si: `_cadastro_base_estoque.xlsx` (EAN, preço
  de venda, fabricante) e `_cadastro_arvore_mercadologica.xlsx`
  (classificação, curva ABC do próprio ERP) — join via etiqueta/código
  interno (`manage.py importar_produtos`). ~44% do cadastro de estoque não
  tem classificação (a árvore não cobre tudo) — importado mesmo assim, só
  fica sem `classificacao`.
- **`apps/vendas`** — `VendaItem`, o relatório "Análise de Venda por Item"
  **por loja e por mês** (`manage.py importar_vendas`, lê todos os
  `vendas *.xls` de `dados/entrada/`) — diferente do relatório anual sem
  quebra que foi mandado primeiro. Base de tudo que precisa saber "quanto
  vendeu onde": Custo x Margem por loja/bandeira/cidade e a tela de
  **Relevância** (`/relevancia/`) — por Classificação, ranking dos itens
  por participação na venda da própria categoria (curva ABC calculada em
  cima da venda real do período, não a Curva Valor/Qtd. do cadastro, que é
  uma foto antiga). Pedido do Gabriel: "quais são os itens mais relevantes
  na classificação x o todo".

`cidade_busca` (nova coluna no robô, adicionada 2026-09-14) é a cidade que
estava ativa na busca (Itabuna/Ilhéus/Ipiaú) — usada aqui como proxy de
região, já que o Preço da Hora só devolve resultados perto da cidade
selecionada.

## Dados de entrada (`dados/entrada/`, gitignored)

- `lojas_config.json` / `concorrentes_config.json` — cópias do robo_cotacao,
  reimportar quando o Gabriel atualizar lá.
- `_cadastro_arvore_mercadologica.xlsx` / `_cadastro_base_estoque.xlsx` —
  cópias das mesmas usadas pelo robo_cotacao/Streamlit.
- `vendas <mês>.xls` (jan-jul/2026, 1 arquivo por mês, todas as lojas, 2
  abas cada por causa do limite de 65.536 linhas do .xls) — relatório
  "Análise de Venda por Item" **com** `Cód. Un. Neg.` (loja) e `Ano-mês`,
  diferente do primeiro arquivo que foi mandado (`vendas por item
  2026.xls`, na raiz de `MONITOR DE PRECOS\`, esse sem quebra — não é mais
  usado, o correto é o `vendas <mês>.xls`).
  - **Faltam agosto e setembro/2026** — não foram mandados ainda
    (confirmar se é porque o mês não fechou ou só não deu tempo de gerar).
- **Pendente:** relatório de histórico de entrada (compra) do ERP, pra
  alimentar a 2ª tela (Análise de Entradas) — ainda não implementada, nem
  a regra de "o que conta como variação relevante" foi definida.

## Status (14/09/2026)

- 25 lojas importadas (bandeira preenchida com o mesmo mapeamento do
  projeto de Apuração de Trade — Ultra Popular = lojas 6/9/10/11/12/13,
  Velanes = as demais — **a confirmar com o Gabriel**, é um projeto
  separado e pode ter mudado).
  - Loja 12 (Jaguaquara) existe no cadastro mas não foi pedida pro robô
    pesquisar — só Itabuna/Ilhéus/Ipiaú por ora. Confirmar se entra também.
- Captação sincronizada: 9.787 preços (só Itabuna até agora — Ilhéus/Ipiaú
  entram sozinhos conforme o robô completa as próximas passadas, ver
  `robo_cotacao/agendador_termos.py`). 910 itens já têm nosso preço +
  concorrência comparável; 383 hoje mais caros que o concorrente mais barato
  da região.
- **Relevância por Classificação implementada** (`/relevancia/`): 550.677
  linhas de venda (jan-jul/26, todas as lojas) cruzadas com 39.854 produtos
  do cadastro (24.595 com classificação via árvore mercadológica, 17.508
  só com EAN/preço, sem classificação — cadastro incompleto no ERP, não é
  bug). 20 classificações (nível logo abaixo de "ARVORE NOVA"), cada uma
  com ranking de itens por % de participação na própria categoria +
  marcação "relevante" (curva ABC calculada na venda real, até 80%
  acumulado). Maior classificação por venda: Propagado (R$ 9,7M no
  período).
- Custo x Margem por loja/bandeira/cidade: dados já disponíveis
  (`VendaItem.venda/custo/lucro`), tela ainda não construída — próximo
  passo natural, avisar se é pra fazer agora.
- Análise de Entradas: nem o relatório nem a regra de "variação relevante"
  foram definidos ainda.
