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
  - **ACHADO 14/09/26 (resolvido):** `vendas fevereiro/março/abril/maio/
    junho.xls` do 1º envio eram todos a MESMA exportação de janeiro por
    dentro (`Ano-mês` = '2026-01' nos 5, conferido linha a linha) —
    Gabriel reexportou depois.
  - **ACHADO 15/09/26: 3 dos arquivos reexportados vieram com o
    relatório ERRADO** (sem a coluna `Ano-mês` — 12 colunas em vez de
    13, layout do relatório "sem quebra" que não é mais usado). Não é
    duplicata dessa vez, é FALTA de coluna — importar isso às cegas teria
    misturado `codigo_erp` com a descrição do produto, porque o
    importador lê por POSIÇÃO da coluna, não pelo nome. Conferido
    cabeçalho linha a linha de cada arquivo antes de importar (não só o
    nome), then descartado o que não servia:
    - `vendas maio 2026.xls`, `vendas julho 2026.xls`, `vendas agosto
      2026.xls` — **sem coluna Ano-mês, não importados.**
    - `vendas fevereiro 2026.xls`, `vendas marco 2026.xls`, `vendas
      abril 2026.xls` — layout certo, importados com sucesso.
  - **Estado real hoje: jan/fev/mar/abr/jul importados (386.140 linhas)**
    — maio, junho e agosto ainda não têm dado utilizável, setembro nunca
    foi mandado. **Pendente: Gabriel reexportar maio/junho/agosto com o
    relatório "Análise de Venda por Item" COM quebra por loja e
    Ano-mês** (mesmo relatório que gerou fev/mar/abr certos dessa vez —
    conferir que a opção de quebra por mês está marcada antes de
    exportar).
- **Pendente:** relatório de histórico de entrada (compra) do ERP, pra
  alimentar a 2ª tela (Análise de Entradas) — ainda não implementada, nem
  a regra de "o que conta como variação relevante" foi definida.

## robo_cotacao (15/09/26, ver README/commits de lá pro detalhe completo)

Achados nessa sessão que afetam diretamente o que chega aqui:
- **Bug real corrigido: seleção de cidade errada.** `definir_localizacao`
  sempre clicava na 1ª sugestão de município ao trocar de cidade, mas a
  lista não vem ordenada por melhor match — digitar "Ipiaú" sugeria
  `['IBIPITANGA', 'IPIAÚ', 'IPIRÁ', 'PARIPIRANGA']`, então o robô vinha
  selecionando Ibipitanga (cidade vizinha errada). Pego antes de
  qualquer captação real de Ipiaú acontecer (a rotação multi-cidade
  entrou em produção no mesmo dia). Itabuna/Ilhéus não tinham esse
  problema (sugestão única).
- **Rodízio de cidade por lote** (era só depois de uma volta completa
  nos 4305 termos — levaria semanas pra Ilhéus/Ipiaú começarem). Agora
  intercala Itabuna → Ilhéus → Ipiaú a cada execução (a cada 30min),
  mesmo volume de interações/hora.
- **Atalho de sessão por cidade:** a cidade escolhida fica em
  `sessionStorage` do navegador (não cookie/localStorage), salva depois
  de definir a localização e reaproveitada na próxima execução daquela
  cidade (injeta + `page.reload()`) em vez de refazer o fluxo do modal —
  medido ~8s → ~3s, com fallback automático pro fluxo normal se não
  bater.
- Considerado usar proxy pra paralelizar as 3 cidades de verdade (em vez
  de intercalar) — pesquisado preço real (~R$300-600+/mês), descartado
  por ora: custo recorrente não compensa pra um robô que já funciona,
  ainda mais contra um portal do governo.

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
- Captação sincronizada (15/09, depois dos fixes do robô): **10.428
  preços — Itabuna 10.272, Ilhéus 151, Ipiaú 5.** Ilhéus/Ipiaú acabaram
  de começar (rodízio por lote entrou em produção hoje) — vão crescer
  sozinhos a cada execução do robô, sem precisar de nada daqui. 910
  itens já têm nosso preço + concorrência comparável em Itabuna; 383
  hoje mais caros que o concorrente mais barato da região (Ilhéus/Ipiaú
  ainda não têm volume suficiente pra aparecer no comparativo).
- **Relevância por Classificação** (`/relevancia/`) e **Custo x Margem**
  (`/custo-margem/`) implementadas — dado real agora é **jan/fev/mar/
  abr/jul (386.140 linhas)**, não mais só jan+jul. Cruzadas com 71.643
  produtos do cadastro (44.707 com classificação). Custo x Margem: venda
  R$ 18,2M, custo R$ 12,8M, lucro R$ 5,5M, margem geral 29,9% (vai mudar
  de novo quando maio/junho/agosto entrarem certos). Loja 12 (Jaguaquara,
  fechada) aparece marcada mas não escondida.
- Análise de Entradas: nem o relatório nem a regra de "variação relevante"
  foram definidos ainda.
- **Tema escuro** aplicado globalmente (`templates/base.html`) — Gabriel
  viu as telas pela 1ª vez e pediu, achou o claro difícil de ver.
- **Monitor de Preço: identificação de loja/concorrente + filtros novos**
  (mesma sessão, depois do Gabriel ver a tela): antes só mostrava a REDE
  ("Pague Menos (+1)"), não dava pra saber qual loja física, nem se o
  "+1" era outra loja da mesma rede ou outro concorrente.
  - `manage.py vincular_lojas_captacao` (novo, roda automático no fim de
    `sincronizar_captacao`): casa `PrecoCaptado` de rede='nossa' com uma
    `Loja` específica pelo número da rua no endereço (o robô não distingue
    qual loja é qual, só a bandeira — mas o endereço captado tem número
    específico). **1.807 de 2.361 registros vinculados (76%)** — resto
    fica "loja não identificada" (ambíguo ou sem candidata), sem quebrar
    a tela.
  - `manage.py geocodificar_concorrentes` (novo, manual — demora minutos,
    respeita 1 req/s da Nominatim): geocodifica endereço de concorrente,
    reimplementando a MESMA lógica já validada em
    `robo_cotacao/mapa_concorrentes.py` (2 bugs reais já corrigidos lá,
    replicados aqui). **29 de 43 endereços únicos geocodificados.**
    Distância real loja-nossa x concorrente calculada via haversine; sem
    geocodificação, mostra só a distância até o centro da cidade (que já
    existia).
  - Filtro por Subclassificação (nível 3 da árvore mercadológica, novo
    campo `Produto.subclassificacao`) além da Classificação (nível 2, já
    existia). Filtro "mais caro / mais barato que a concorrência".
  - Cada linha agora mostra a lista completa (não só resumo): nossas
    lojas com preço+distância, concorrentes com nome real+rede+preço+
    distância — expansível (`<details>` nativo, sem JS).
- **Monitor de Preço: filtro por Loja (mesma sessão, rodada seguinte)**
  — Gabriel notou que a distância do concorrente não dizia de QUAL das
  nossas lojas era (quando o EAN tem preço em 2+ lojas nossas, a
  distância vinha só da 1ª vinculada, sem rótulo). Voltou pro objetivo
  real: 22-24 lojas, cada uma com seu preço, "todas as opções de análise"
  (por loja, cidade, classificação). Resolvido:
  - Novo filtro "Loja" (dropdown das 24 lojas ativas, mostra bandeira+
    cidade; marca "(sem dado ainda)" as que não têm captação vinculada —
    10 das 24 hoje). Selecionando 1 loja, a linha vira preço/distância
    daquela loja específica só (sem lista "N loja(s)" ambígua).
  - Sem loja selecionada (visão agregada por bandeira/cidade, mantida):
    quando todas as nossas lojas daquele EAN resolvem pra 1 loja física
    só (comum hoje), mostra a distância rotulada ("0,8 km de Loja 3").
    Quando 2+ lojas distintas estão envolvidas, o resumo não mostra mais
    nenhum número solto (era enganoso) — o detalhe expandido mostra a
    distância calculada em relação a CADA loja nossa individualmente.
