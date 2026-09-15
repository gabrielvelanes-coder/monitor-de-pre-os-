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
- `vendas <mês>.xls` (todas as lojas, 2 abas cada por causa do limite de
  65.536 linhas do .xls) — relatório "Análise de Venda por Item" **com**
  `Cód. Un. Neg.` (loja) e `Ano-mês`, diferente do primeiro arquivo que
  foi mandado (`vendas por item 2026.xls`, na raiz de `MONITOR DE
  PRECOS\`, esse sem quebra — não é mais usado).
  - **ACHADO 14/09/26: só `vendas janeiro.xls` e `vendas julho.xls` têm
    dado de verdade.** `vendas fevereiro/março/abril/maio/junho.xls` têm
    nomes diferentes mas são todos a MESMA exportação de janeiro por
    dentro (`Ano-mês` = '2026-01' nos 5, conferido linha a linha, não só
    pelo título) — o Gabriel deve ter reexportado sem trocar o filtro de
    mês no ERP antes de salvar. Só entrou no banco 1 cópia de cada mês
    real (a constraint `loja+codigo_erp+ano_mes` absorveu as duplicatas
    silenciosamente) — **156.042 linhas reais** (78.927 jan + 77.115 jul),
    não os "550.677 linhas jan-jul" que constavam aqui antes. **Pendente:
    Gabriel reexportar fev/mar/abr/mai/jun corretamente.**
  - **Faltam agosto e setembro/2026** — setembro só vai até 14/09 (mês em
    andamento), agosto ainda não foi mandado.
- **Pendente:** relatório de histórico de entrada (compra) do ERP, pra
  alimentar a 2ª tela (Análise de Entradas) — ainda não implementada, nem
  a regra de "o que conta como variação relevante" foi definida.

## Status (15/09/2026)

- 25 lojas importadas (bandeira confirmada pelo Gabriel: Ultra Popular =
  lojas 6/9/10/11/12/13, Velanes = as demais — mesmo mapeamento do projeto
  de Apuração de Trade).
  - **Loja 12 (Jaguaquara) está fechada** (confirmado pelo Gabriel
    15/09/26) — campo `Loja.ativa=False` adicionado ao model (mantida no
    cadastro pelo histórico de vendas, fora das telas ao vivo). Nunca
    entrou na rotação do robô (só Itabuna/Ilhéus/Ipiaú), então não afetava
    o Monitor de Preço; afetaria uma futura tela de Custo x Margem se
    não tivesse sido marcada.
- **Rotação de cidade do robô trocada 15/09/26** (Gabriel achou a
  captação de Ilhéus/Ipiaú baixa demais): antes, cada cidade só entrava
  na rotação quando uma VOLTA COMPLETA de 4305 termos terminava — no
  ritmo real (bloqueios intercalados), Ilhéus levaria ~2-3 semanas pra
  começar a captar QUALQUER coisa. Trocado pra rodízio por lote
  (Itabuna → Ilhéus → Ipiaú → Itabuna a cada execução), mesmo volume de
  interações por hora/mesmo risco de bloqueio — agora as 3 cidades
  recebem dado em paralelo desde a próxima execução agendada, em troca
  de cada cidade levar ~3x mais tempo pra fechar o catálogo inteiro.
  Ver comentário em `robo_cotacao/agendador_termos.py`.
- Captação sincronizada: 10.128 preços (ainda só Itabuna no banco — o
  efeito da mudança de rotação só aparece nas próximas sincronizações).
  910 itens já têm nosso preço + concorrência comparável; 383 hoje mais
  caros que o concorrente mais barato da região (números vão mudar
  quando Ilhéus/Ipiaú entrarem).
- **Relevância por Classificação implementada** (`/relevancia/`): dado real
  hoje é só **jan + jul/26** (ver achado acima), 156.042 linhas, cruzadas
  com 71.643 produtos do cadastro (44.707 com classificação, usando a
  versão mais completa dos cadastros — `BASE CADASTRO COM GRUPOS/EAN.xlsx`
  do projeto de Perdas, bem maiores que as cópias que estavam no
  robo_cotacao). 20 classificações (nível logo abaixo de "ARVORE NOVA"),
  cada uma com ranking de itens por % de participação na própria categoria
  + marcação "relevante" (curva ABC calculada na venda real, até 80%
  acumulado). Números de venda por classificação **vão mudar** assim que
  fev-jun entrarem de verdade.
- **Custo x Margem implementada** (`/custo-margem/`): 3 níveis (por
  loja/por bandeira/por cidade) a partir de `VendaItem.venda/custo/lucro`,
  mesmos filtros de mês/bandeira/cidade da tela de Relevância. Tabela "por
  loja" ordenada com a menor margem primeiro (só destaca, não recomenda
  nada). Loja 12 (Jaguaquara, fechada) aparece marcada "fechada" mas não é
  escondida — mantém o histórico de venda visível. Números de hoje (jan+jul
  reais): venda R$ 18,2M, custo R$ 12,8M, lucro R$ 5,5M, margem geral 29,9%
  — vão mudar quando fev-jun entrarem de verdade.
- Análise de Entradas: nem o relatório nem a regra de "variação relevante"
  foram definidos ainda.
