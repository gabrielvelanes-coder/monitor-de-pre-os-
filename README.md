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
- **BUG REAL corrigido (mesma sessão): 36% da venda caía em "sem
  classificação".** Gabriel notou que MOUNJARO aparecia sem classificação
  na Relevância mesmo o ERP dele mostrando a classificação certa. Causa:
  "Código" da árvore mercadológica e "Etiqueta" do cadastro de estoque
  não são o mesmo valor pro mesmo produto físico em boa parte dos casos
  (Mounjaro: 124037 vs 104644) — o join por código falhava
  silenciosamente. 26.936 produtos "sem classificação" (R$ 16M em vendas,
  36% do total, a MAIOR "classificação" da tela) tinham 100% um gêmeo com
  a MESMA DESCRIÇÃO já classificado. `importar_produtos` agora usa
  descrição normalizada como fallback quando o código não bate (30
  descrições ambíguas, 0,07%, ficam de fora do fallback). Reimportado:
  "sem classificação" caiu de R$ 16.036.112,48 pra R$ 38.702,59.
- **`USE_THOUSAND_SEPARATOR = True`** (`config/settings.py`) — números
  apareciam sem separador de milhar ("16036112.48"); com pt-br + esse
  flag, formata sozinho em toda a aplicação ("16.036.112,48").
- **Filtro por Bairro (mesma sessão):** Gabriel deu o exemplo de variação
  de preço DENTRO da mesma cidade (leite mais caro num bairro que no
  Centro) — oportunidade que a granularidade por cidade não capturava.
  Novo `manage.py extrair_bairros_captacao` (roda automático no fim de
  `sincronizar_captacao`): o robô não guarda bairro separado, só o
  endereço bruto — extrai via regex (99,6% de acerto, 10.384 de 10.428).
  **Achado no caminho:** o mesmo bairro aparecia grafado com e sem
  acento em capturas diferentes ("SAO CAETANO" 1287x, "SÃO CAETANO"
  229x, provável inconsistência do próprio HTML do Preço da Hora) —
  fragmentava o filtro em 2 opções pro mesmo lugar; normalizado (tira
  acento sempre). Novo filtro "Bairro" na tela, igual Loja/Cidade/
  Classificação (Gabriel confirmou: reusar a tabela existente, não uma
  tela dedicada).
- **Densidade da tabela reduzida** (Gabriel: "não entendi nada" vendo 2
  `<details>` abertos com texto corrido): linha resumida enxuta, "ver
  detalhes" abre painel largo (`<tr colspan>`) com 2 mini-tabelas de
  verdade (Nossas lojas | Concorrentes). Distância ambígua (2+ lojas)
  virou "distância até a loja mais próxima" (1 número, rotulado) em vez
  de listar todas as combinações.
- **Distância "0,91 km do centro" era geocodificação imprecisa
  disfarçada:** 5 das 24 lojas (e vários concorrentes) geocodificam pro
  MESMO ponto exato via Nominatim (não resolve endereço no nível da rua
  em boa parte de Itabuna/Ilhéus/Ipiaú, cai pro centroide do bairro) —
  distância haversine virava 0,0km (falsy no template, caía num
  fallback genérico sem relação com loja nenhuma). Agora rotulado
  explicitamente "mesma região de Loja X (sem precisão de endereço)".
- **Tabela interativa**: ordenar clicando no cabeçalho + busca
  instantânea, `static/js/tabela.js` (mesmo padrão do Painel de
  Ofertas, reimplementado — projetos não compartilham código). Cuidado
  extra: o painel de detalhe (`<tr class="linha-detalhe">`) precisa
  mover/esconder junto da linha-mãe ao ordenar/filtrar.
- **Auditoria 360 (Gabriel pediu depois de achar 2 problemas na mesma
  hora — filtro Classificação trazendo item de outra categoria, e
  "loja não identificada" persistente):**
  - **BUG REAL GRANDE em `apps/produtos`:** o "Código" da árvore
    mercadológica é um identificador INTERNO do ERP que é REAPROVEITADO
    com o tempo pra produtos diferentes (ex. código 78881 = "SAB LIQ
    REXONA..." na árvore, mas "ABS ALWAYS..." no estoque, mais atual —
    zero palavra em comum). O join por código vinha herdando descrição/
    classificação ERRADA silenciosamente — **26.482 produtos (37% do
    catálogo inteiro!)** tinham esse problema, bem maior que o achado
    anterior (que só pegava código SEM nenhum match, não código com
    match ERRADO). Corrigido: quando árvore e estoque não têm nenhuma
    palavra em comum, usa a descrição do estoque (mais atual) e tenta
    recuperar a classificação certa pela descrição (mesmo mecanismo já
    existente). "Sem classificação de verdade" caiu pra 92 produtos.
  - **BUG REAL em `vincular_lojas_captacao`:** comparava número de rua
    por SUBSTRING ("2" in endereço) — número curto batia contra
    QUALQUER endereço que contivesse aquele dígito em outro número
    maior ("128", "1299", "428A", "32"), virando "ambíguo" por engano
    mesmo tendo 1 match exato de verdade. Corrigido pra igualdade exata
    do número extraído. Taxa de vínculo subiu de 85% pra **91%**, zero
    ambíguos (eram 138 falsos positivos).
  - Confirmado que parte do "sem vínculo" restante é dado real
    incompleto, não bug: ex. CARVEDILOL tem 1 registro Ultra Popular em
    endereço que não bate com nenhuma das 2 lojas Ultra Popular
    cadastradas em Itabuna — cadastro de loja incompleto, não erro de
    lógica.
- **Auditoria 360, 2ª rodada — mais 1 bug real + 1 achado de cadastro:**
  - **BUG REAL em `montar_comparativo`:** selecionar Loja + Cidade
    incompatível (loja de uma cidade, filtro de outra) quebrava TODAS
    as comparações de concorrente em silêncio — `nossos_qs` ficava
    restrito à loja (cidade real), mas `conc_qs` aplicava o parâmetro
    de URL por fora, sem relação. "Itens comparados" continuava normal,
    "mais caros" ia pra 0 escondido, sem aviso. Corrigido: loja sempre
    manda na cidade/bandeira, ignora parâmetro de URL conflitante;
    `views.py` também corrigido pra mostrar os dropdowns refletindo a
    loja de verdade.
  - **1092 produtos com EAN='nan'** (string literal, bug do pandas no
    1º loop de `importar_produtos` que não tinha a mesma guarda do 2º)
    — confirmado sem sintoma visível, corrigido por consistência.
  - **Achado de cadastro (não bug):** 194 dos 215 "sem vínculo"
    restantes eram todos o MESMO endereço — "DROGARIA ULTRAPOPULAR" na
    Av. Cinquentenário 428A, Itabuna, endereço que no cadastro
    pertencia à Loja 21 (Velanes). Gabriel confirmou: **Loja 10 (Ultra
    3) mudou pra esse endereço, Loja 21 fechou de vez.** Corrigido no
    `lojas_config.json` (fonte no robô) — Loja 10 com endereço novo,
    Loja 21 `ativa=false`. **Vínculo de loja subiu de 91% pra 99,1%**
    (2.367 de 2.388). Captação resincronizada no processo: 10.585
    preços agora (era 10.428).
- **Maio e junho reenviados e importados (16/09/26)** — 2 bugs reais
  achados em `importar_vendas` no processo:
  - **Colunas trocadas de posição:** o arquivo de maio veio com Loja e
    Ano-mês na ordem invertida (mesmo nome de coluna, posição
    diferente — ERP não exporta sempre igual). Importar por posição
    cega (como era antes) teria lido "2026-05" como código de loja.
    Corrigido: `importar_vendas` agora detecta a posição de cada
    coluna pelo NOME (Ano-mês/Cód. Un. Neg./Cód. Barras.Etiq./etc. são
    todas únicas — só as 3 colunas "%" repetidas, que nem usamos, são
    ambíguas). A 2ª aba de cada arquivo não tem cabeçalho de texto
    (limite de 65.536 linhas do .xls) — reaproveita a posição
    detectada na 1ª aba do mesmo arquivo.
  - **Código de loja virava "22.0"/"23.0":** quando o arquivo tem linha
    em branco/"Total" na coluna de loja, o pandas lê a coluna inteira
    como float (não dá pra ter NaN num int) — nunca batia com o
    cadastro (2 dígitos). Perdeu TODA a 2ª aba de maio na 1ª tentativa
    (10.246 linhas, todas de lojas 22+). Mesmo tratamento que já
    existia pro código de barras, aplicado aqui também.
  - Resultado: **maio 75.780 linhas, junho 74.934 linhas** — jan-jul
    completos agora, **536.854 linhas** no total.
- **Agosto reenviado e importado (16/09/26, mesmo dia)** — "vendas novo
  agosto 2026.xls", relatório certo dessa vez (13 colunas, Ano-mês
  '2026-08' confirmado linha a linha). **74.558 linhas.** Mesmo
  importador corrigido (nome de coluna) deu conta sem ajuste nenhum.
  **jan-agosto completos agora, 611.412 linhas no total.**

## Pendências (16/09/2026)

Lista consolidada do que falta/está esperando decisão — atualizar aqui
sempre que resolver ou surgir uma nova, em vez de só no meio do log
acima.

**Dados de vendas (bloqueado no Gabriel):**
- ~~Maio/junho/agosto~~ — **resolvido 16/09/26.** Todos os 3 reenviados
  no relatório certo e importados (2 bugs reais achados e corrigidos no
  importador nesse processo — colunas trocadas de posição + loja
  "22.0", ver log acima). **jan-agosto completos, 611.412 linhas.**
- **Setembro** nunca foi mandado (nem parcial) — só falta esse.

**Backup/infraestrutura (achado 16/09/26, Gabriel perguntou "se meu PC
quebrar, perco tudo?"):**
- `monitor-precos` **não tem repositório remoto** (GitHub) — todo o
  histórico de commits só existe no disco local. Risco real de perda
  total se a máquina falhar.
- `robo_cotacao` tem remoto (GitHub, `gabrielvelanes-coder/robo_cotacao`)
  mas estava **5 commits atrasado** (fixes de 15-16/09 não enviados) +
  2 arquivos modificados sem commit (`app.py`, `catalogo_produtos.py`,
  não são mudanças dessa sessão).
- Os bancos de dado de verdade (`db.sqlite3` 146MB, `_precos_continuos.
  sqlite3` 8MB) **nunca estão no Git** (é dado, não código, gitignored
  de propósito) — a única proteção é o OneDrive sincronizar direito, o
  que pode atrasar num banco escrito a cada 30min pelo robô. Sem
  confirmação de que o sync está 100% em dia.
- Perguntado ao Gabriel se quer que eu já envie os commits pendentes do
  robô e crie um repositório novo pro monitor-precos — aguardando
  resposta.

**Telas ainda não construídas:**
- **Análise de Entradas** — nem o relatório de origem (histórico de
  entrada/compra do ERP) nem a regra de "o que conta como variação
  relevante" foram definidos. Gabriel disse "depois vemos entrada"
  (15/09/26), foco era só Monitor de Preço.
- **Gráfico de dispersão/posicionamento** — quadrantes Margem x
  Diferença de preço vs. concorrência, 1 ponto por produto, filtro por
  loja, interativo. Gabriel pediu explicitamente pra **deixar em
  pendência** (16/09/26) — cruza `apps/monitor` (preço) com
  `apps/vendas` (margem), hoje independentes; vai precisar de app/tela
  nova de verdade, não é extensão pequena.

**Decisões de produto em aberto:**
- **Histórico/série temporal** — hoje o Monitor de Preço só mostra o
  estado ATUAL (snapshot), sem guardar histórico pra responder "estamos
  ficando mais caros ao longo do tempo?". Discutido quando Gabriel
  perguntou se a ferramenta está "boa pra decisão" — é mudança de
  arquitetura (guardar séries temporais), decisão dele se entra na v1.
- **Acesso/deploy** — hoje só roda via `manage.py runserver` na máquina
  do Gabriel (`DEBUG=True`, sem host configurado). Se for pra outras
  pessoas do Grupo Velanes acessarem (gerente de loja, comprador),
  precisa decidir hospedagem. Perguntado, sem decisão ainda.

**Manutenção recorrente (não é bug, é rotina):**
- `manage.py geocodificar_concorrentes` **não roda automático** (só
  `vincular_lojas_captacao`/`extrair_bairros_captacao` rodam sozinhos
  no fim de `sincronizar_captacao`) — precisa rodar manual de vez em
  quando conforme aparecem concorrentes novos na captação (hoje 29 de
  43 endereços únicos geocodificados).
- Cobertura de Ilhéus/Ipiaú ainda crescendo (rodízio por lote do robô
  entrou em produção 15/09/26) — números de comparação nessas 2 cidades
  ainda vão crescer sozinhos, sem precisar de nada daqui.
