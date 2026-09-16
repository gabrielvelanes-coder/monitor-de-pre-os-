# Monitor de Preço de Mercado

Painel Django para **monitorar** (não recomendar) preço nosso x concorrência,
usando os dados que o [robo_cotacao](../../robo_cotacao) já capta todo dia no
Preço da Hora — e, numa 2ª tela ainda não construída, sinalizar variações de
preço de entrada (compra) que merecem olhar.

Projeto separado, git próprio (não reaproveita código do robo_cotacao nem dos
outros painéis — só dados e regras de negócio já validadas).

Repositório remoto: https://github.com/gabrielvelanes-coder/monitor-de-pre-os-
(criado e conectado 16/09/26, ver seção Pendências → Backup/infraestrutura).

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
- **Setembro (parcial) importado (16/09/26, mesmo dia)** — "vendas
  parcial setembro.xls", 1 aba só (mês em andamento, não bate o limite
  de linhas do .xls). **54.388 linhas**, sem ajuste no importador.
  **jan-setembro(parcial), 665.800 linhas no total.**
- **Sincronização automática + botão manual (16/09/26).** Gabriel
  notou que "itens comparados" não subia desde o dia anterior — achado:
  a captação não era resincronizada com o robô há 14h (última vez
  19h31 do dia anterior), mesmo o robô continuando a captar normal.
  Ninguém tinha ficado de rodar `sincronizar_captacao` manualmente.
  Resolvido com 2 coisas juntas:
  - Botão **"Sincronizar agora"** no topo do Monitor de Preço (nova
    view `sincronizar_agora`, POST) — roda a sincronização na hora,
    sem precisar de terminal.
  - **Tarefa Agendada do Windows** `VelanesP_SincronizarCaptacao`
    (mesmo padrão do robô), rodando `sincronizar_captacao` sozinha a
    cada 30min — testado rodando via Agendador de verdade
    (`LastTaskResult=0`), não só manual.
  - A tela agora sempre mostra **"dado mais recente: há N min"** no
    topo — a defasagem fica visível em vez de escondida.
- **3 ajustes de UX depois da sincronização (16/09/26, mesmo dia):**
  - **Cartões viraram filtro clicável.** Os 3 cartões de resumo (Itens
    comparados / Mais caros / Sem concorrente) agora são links que
    aplicam `situacao` na URL, preservando os outros filtros ativos.
    Os números dos próprios cartões continuam mostrando sempre o
    panorama GERAL (não encolhem ao clicar em "Sem concorrente", por
    exemplo) — 2ª chamada a `montar_comparativo(situacao=None)` só
    pra isso quando um filtro de situação está ativo
    (`linhas_para_cartoes` em `views.py`). Testado ao vivo: os 2
    filtros (mais_caro e sem_concorrente) mudam URL, dropdown e tabela
    corretamente.
  - **Botão "Sincronizar agora" virou ícone.** Era texto grande, agora
    é um círculo pequeno (⟳) no canto — `.botao-icone` em
    `base.html`.
  - **Notificação some sozinha.** Mensagens de sucesso/erro (ex. "10993
    preço(s) sincronizado(s)") desaparecem depois de 4s, CSS puro
    (`.aviso-some` + `@keyframes aviso-desaparecer`, sem JS). Validado
    via Web Animations API (`getAnimations()`) forçando o relógio da
    animação até o fim — o Chrome controlado por automação trava o
    avanço de tempo de animações CSS em abas sem foco real de janela,
    então não dava pra ver o fade rolar "ao vivo" no teste, mas o
    resultado final (opacity 0, visibility hidden no fim do delay+
    duração) bateu certinho.
- **Curva de quantidade vendida por mês (16/09/26, mesmo dia).** Gabriel
  confirmou que queria "curva quantidade das nossas lojas" — soma de
  `VendaItem.itens` por `ano_mes`, das lojas vinculadas ao EAN/cidade
  daquela linha. Decisões de design:
  - **Onde:** dentro do mesmo painel de detalhe ("ver detalhes"), não
    tela nova nem coluna nova na tabela principal — segue a mesma lógica
    do redesign anterior (painel largo já existe, só ganhou uma 3ª
    seção abaixo das 2 tabelas).
  - **Como:** SVG puro gerado em Python (`svg_curva_quantidade` em
    `services.py`), sem lib nova — mesma filosofia do Haversine em
    Python puro já usado pra distância. 1 linha só (soma agregada, não
    1 linha por loja — evita virar 10 linhas coloridas pra item com
    "méd. de 10 lojas"), sem eixo numerado, valor exato só no hover
    (`<title>` nativo do SVG), rótulo direto só no último ponto
    (seletivo, não em todos).
  - **Mês corrente vem tracejado/vazado** — comparado com
    `timezone.now()`, não com "setembro" fixo (continua funcionando
    sozinho em outubro) — senão o mês parcial pareceria queda de venda.
  - **Removida a trava do link "ver detalhes"** (antes só aparecia com
    2+ lojas ou 2+ concorrentes) — agora toda linha tem a curva pra
    mostrar (mesmo que "sem dado de venda"), então o link sempre
    aparece.
  - Testado com 3 casos: EAN com 6 meses de dado, EAN com 9 meses
    completos, e EAN sem nenhum `VendaItem` vinculado (mostra "Sem dado
    de venda registrado pra esse produto nessas lojas." em vez de
    gráfico vazio).
  - **Corrigido no mesmo dia:** a 1ª versão somava tudo numa linha só.
    Gabriel viu o exemplo do ATROVENT (Loja 2/Loja 4/Loja 3) e pediu a
    curva de CADA loja, não o total -- trocado por 1 sparkline compacta
    por linha, dentro da própria tabela "Nossas lojas" (coluna nova
    "Qtd. vendida/mês"), sem precisar de legenda/cor por loja porque o
    nome já está na linha. Escala até 10 lojas (testado com COLETOR
    UNIVERSAL) sem virar bagunça -- cada sparkline é independente,
    função `svg_sparkline_quantidade` (services.py), 1 query só
    agrupada por loja+mês (`montar_curvas_quantidade_por_loja`).
- **Base do histórico de preço criada (16/09/26, mesmo dia).** Gabriel
  aprovou o caminho 1 (tabela de histórico separada, 1 snapshot por dia,
  retenção de 1 ano). Criado:
  - **Modelo `PrecoHistorico`** (`apps/captacao/models.py`) — mesmos
    campos-chave de `PrecoCaptado` (ean, cidade, rede, estabelecimento,
    endereço, loja, preço) + `data` (DateField, 1 por dia, não por
    sincronização — senão vira milhões de linhas por semana à toa).
  - **`manage.py snapshot_precos_historico`** — copia o estado do dia de
    `PrecoCaptado` pra `PrecoHistorico`, idempotente (rodar 2x no mesmo
    dia não duplica, testado: 11.083 gravados na 1ª vez, 0 na 2ª) e já
    apaga sozinho quem passou de 1 ano.
  - **Tarefa Agendada `VelanesP_SnapshotHistoricoPrecos`**, 1x/dia às
    23:30 (mesmo padrão das outras 2 tarefas do projeto) — testada rodando
    de verdade via Agendador (`LastTaskResult=0`), não só manual.
  - **O gráfico de evolução em si ainda não foi construído** — só tem 1
    dia de histórico até agora (16/09/26), um gráfico de 1 ponto não diz
    nada. Fica pendente até acumular alguns dias/semanas de dado; a
    ideia é reaproveitar o mesmo padrão da curva de quantidade (sparkline
    SVG dentro do painel de detalhe, sem tela nova) quando tiver dado
    suficiente pra valer a pena.
- **Refino visual (16/09/26, mesmo dia).** Gabriel achou o layout "feio"
  e pediu algo mais "tecnológico" — antes de mexer no código, montei uma
  comparação visual (Artifact, com o mesmo dado real de um print dele:
  Loja 6/10/23/2/4/14 + 14 concorrentes) mostrando estilo atual x
  proposta lado a lado. Ele aprovou ("pode fazer") e apliquei de
  verdade — mudança em `base.html`, então vale em TODAS as telas
  (Monitor, Relevância, Custo x Margem), não só o painel de detalhe:
  - **Inter + JetBrains Mono** (Google Fonts) — texto em Inter, todo
    número (preço/%/distância/contagem) em monoespaçada com
    `tabular-nums`, alinhando pela casa decimal. Números grandes de
    cartão (hero, "1.038") continuam em Inter proporcional — mono só
    pra número em coluna, não pra número de destaque.
  - **Tabelas sem grade cheia** — trocada a caixa de borda em toda
    célula por só uma linha fina embaixo de cada linha; cabeçalho troca
    o fundo cinza por texto pequeno com um traço curto na cor de
    destaque embaixo (`::after` de 2px).
  - **Barra de destaque no hover** — pseudo-elemento na borda esquerda
    da 1ª célula de cada linha, opacidade 0→1 no `:hover`, sinaliza que
    a linha tem mais informação atrás ("ver detalhes").
  - **Distância precisa x imprecisa vira sinal visual** — classes
    `.dist-precisa`/`.dist-vaga` com um pontinho (azul com brilho vs
    apagado+itálico) — informação que já existia (`distancia_precisa`
    em `services.py`) mas só aparecia em texto cinza pequeno, igual pra
    os dois casos.
  - **Sparkline com curva suave + gradiente + brilho** — reescrita
    `svg_sparkline_quantidade`: em vez de linha reta entre os pontos,
    curva suave (`_caminho_suave`, técnica de ponto médio); área
    sombreada em gradiente embaixo da linha; ponto mais recente com
    halo de brilho atrás. **Simplificação consciente:** a versão
    anterior tracejava o último trecho quando o mês era parcial/corrente
    — com curva suave isso exigiria reconstruir o path manualmente (a
    continuidade da curva depende do trecho anterior); mantido só o
    marcador vazado pro mês parcial, que já comunica a mesma coisa sem
    essa complexidade.
  - Testado nas 3 telas (Monitor de Preço, Relevância, Custo x Margem)
    — nenhuma quebrou com a mudança global.
- **Cobertura por cidade e endereço da Loja 18 corrigido (16/09/26,
  mesmo dia).** Gabriel notou 2 coisas:
  - Perguntou se algum EAN aparece em mais de 1 cidade — quase nunca
    (só 3 de 1.040 EANs nossos). Motivo real, não bug: Itabuna tem
    1.000 EANs captados, Ilhéus 35, Ipiaú 8 — cobertura ainda MUITO
    desigual (rodízio por lote do robô ainda enchendo Ilhéus/Ipiaú, ver
    pendência mais abaixo). Sobreposição entre cidades vai crescer
    sozinha conforme o robô capta mais lá.
  - Apontou um "loja não identificada" (RETEMIC, Ilhéus) que devia ser
    da Loja 18. Cadastro tinha "AV UBAITABA, 1"; robô captava
    "AVENIDA UBAITABA 1123". **1ª hipótese errada:** achei que o erro
    era do robô/Preço da Hora. Gabriel apontou a planilha-fonte
    (`DADOS GRUPO VELANES ATUALIZADO 2025.xlsx`) — que TAMBÉM tinha
    "1". Consultado o CNPJ da loja (14.211.106/0005-72) via Receita
    Federal (BrasilAPI): endereço oficial é **1123**, batendo com o
    robô. O "1" era erro de digitação na planilha interna mesmo.
    Corrigido `lojas_config.json` (monitor-precos E robo_cotacao, os 2
    têm cópia) e rodado `vincular_lojas_captacao` de novo — vínculo
    subiu de 99,1% pra **99,3%** (2.459/2.477). **Lição:** quando 2
    fontes externas independentes (robô/governo E Receita Federal)
    concordam contra 1 fonte interna, vale conferir a fonte interna
    antes de assumir que o dado externo está errado.
- **Nova tela "Configuração de Concorrentes" (16/09/26, mesmo dia).**
  Gabriel questionou o conceito de "6/7 concorrentes curados" — não
  queria uma lista fixa, queria ver TODO estabelecimento captado (414
  ficavam escondidos como "sem rede identificada", alguns com bastante
  volume — ex. FARMACIA ULTRA ECONOMICA, 289 registros, mais que "São
  Paulo" que já era curada) e poder marcar/desmarcar quem conta.
  - `Rede.ativa` (novo campo, default `True`) — só Redes
    tipo=concorrente **ativas** entram no Monitor de Preço
    (`montar_comparativo` ganhou `rede__ativa=True` no filtro).
  - `manage.py descobrir_concorrentes` (novo, encadeado no fim de
    `sincronizar_captacao`) — cria 1 Rede por estabelecimento sem
    classificação, sempre **inativa** por padrão (não muda nada sozinho
    na hora, só dá visibilidade). 414 descobertos na 1ª rodada.
  - Tela nova `/concorrentes/` (menu lateral, grupo Preço) — tabela
    interativa (busca + ordenação, reaproveitando `tabela.js`) com 1
    checkbox por linha, ordenada por ativos primeiro e depois volume de
    registros (pra ele revisar os maiores primeiro). Testado
    end-to-end: marcar/salvar funciona, reflete no Monitor de Preço na
    hora, sobrevive a reload.
  - **Decisão de quais ativar fica com o Gabriel** — a implementação só
    deu a ferramenta; nenhum dos 414 foi ativado por conta própria.
- **Investigação "Ipiaú muito estranho" (16/09/26, mesmo dia) — 2 bugs
  reais achados e corrigidos:**
  1. **`Loja.cidade` da Loja 13 (única loja em Ipiaú) sem acento**
     ("Ipiau" em vez de "Ipiaú") — inconsistente com o resto do sistema
     (robô, `PrecoCaptado.cidade_busca`, sempre acentuado). Filtrar o
     Monitor de Preço por "Loja 13" retornava **0 linhas sempre**,
     silenciosamente — mesma classe de bug de acento/grafia já corrigida
     antes pra outras lojas. Corrigido `lojas_config.json` (2 cópias:
     monitor-precos e robo_cotacao) + reimportado + revinculado: Ipiaú
     foi de 0/8 pra **8/8** vinculado, vínculo geral subiu de 99,3% pra
     **99,6%**.
  2. **Bairro errado quando a rua/rodovia tem número no próprio nome**
     (ex. "RUA 2 DE JULHO, S/N" ou "RODOVIA BR 415, S/N") — a regex de
     extração de bairro pegava esse número (parte do NOME, não da
     numeração predial) como se fosse número do imóvel, bagunçando o
     bairro capturado ("DE JULHO S/N CENTRO", "S/N PARQUE VERDE" etc.).
     Corrigido priorizando "S/N" literal quando presente. Afetava
     **304 registros** — não só a Loja 13; os 2 maiores casos eram
     trechos da BR 415 e BR 101 em Itabuna.
  - **Confirmado depois da correção:** captação de Ipiaú está normal e
    ativa — 110 registros no total (8 nossa/Loja 13 + 102 concorrente),
    91 EANs distintos, 28 estabelecimentos, última passada do robô
    poucas horas antes de checar. Volume bem menor que Itabuna (ainda
    "enchendo", rodízio por lote entrou em produção só no dia anterior,
    15/09/26) — não é captação parada nem quebrada, só cobertura jovem.

## Pendências (16/09/2026)

Lista consolidada do que falta/está esperando decisão — atualizar aqui
sempre que resolver ou surgir uma nova, em vez de só no meio do log
acima.

**Dados de vendas (bloqueado no Gabriel):**
- ~~Maio/junho/agosto~~ — **resolvido 16/09/26.** Todos os 3 reenviados
  no relatório certo e importados (2 bugs reais achados e corrigidos no
  importador nesse processo — colunas trocadas de posição + loja
  "22.0", ver log acima). **jan-agosto completos, 611.412 linhas.**
- ~~Setembro~~ — **resolvido (parcial) 16/09/26.** 54.388 linhas do mês
  em andamento. **jan-setembro(parcial), 665.800 linhas no total.**
  ~~Atenção pro futuro: apagar o parcial antes do final~~ — **correção
  16/09/26 (mesmo dia): nota anterior estava errada.** Reli
  `importar_vendas.py` com calma: o `bulk_create` usa
  `update_conflicts=True` com
  `unique_fields=["loja","codigo_erp","ano_mes"]` — é upsert de
  verdade, não só insert. Quando o arquivo final de setembro chegar,
  **é só importar por cima** (mesmo processo de sempre) — as linhas
  batem na mesma chave (loja+código+mês) e são atualizadas, não
  duplicadas. Não precisa apagar nada antes.

**Backup/infraestrutura (achado 16/09/26, Gabriel perguntou "se meu PC
quebrar, perco tudo?"):**
- ~~`monitor-precos` sem repositório remoto~~ — **resolvido 16/09/26.**
  Gabriel criou https://github.com/gabrielvelanes-coder/monitor-de-pre-os-
  (`gh` CLI não está instalado nessa máquina, então ele criou pelo site e
  rodou `git remote add` + `git push -u origin master` manualmente no
  PowerShell — o `git remote add` daqui do Claude Code foi bloqueado pelo
  classificador de modo automático). 284 objetos enviados, histórico
  completo (commit `207258c`) confirmado nos dois lados.
- ~~`robo_cotacao` 5 commits atrasado~~ — **resolvido 16/09/26**, `git
  push origin main` enviado sem problema (repositório já existia).
  Ainda tem 2 arquivos modificados sem commit lá (`app.py`,
  `catalogo_produtos.py`, não são mudanças dessa sessão) — não mexido.
- ~~Bancos de dado sem backup confiável~~ — **resolvido 16/09/26,
  parcialmente.** Confirmado ao vivo: o ícone do Explorer mostrava
  "sincronizando" (não o check verde) no `db.sqlite3` bem depois da
  última mudança — o banco fica sendo reescrito toda hora (toda
  importação, o robô a cada 30min), então o OneDrive nunca "fecha" o
  upload dele de verdade. Criado `backup_bancos.py` (monitor-precos):
  tira uma cópia ESTÁTICA de cada banco via backup API do SQLite
  (seguro com o banco em uso) em `OneDrive\Área de Trabalho\BACKUPS
  DB\` — como a cópia parada nunca muda de novo, o OneDrive consegue
  sincronizar ela até o fim. Mantém os últimos 10 backups de cada,
  apaga os mais velhos. Testado: integridade OK, contagem de linhas
  bate com o banco real. **Decisão do Gabriel (16/09/26): rodar
  manual, não automatizar** (`python backup_bancos.py` dentro de
  `monitor-precos/`) — rodar ao terminar sessões com bastante
  importação/mudança de dado, não precisa de Tarefa Agendada.

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
- ~~Curva de quantidade das nossas lojas~~ — **resolvido 16/09/26.**
  Implementada dentro do painel "ver detalhes" (ver log acima).
- **Revisar Configuração de Concorrentes (nova, 16/09/26)** — tela
  `/concorrentes/` criada com 414 estabelecimentos descobertos
  automaticamente, todos **inativos** por padrão (não contam no Monitor
  de Preço ainda). Gabriel precisa entrar lá e marcar quem considera
  concorrente de verdade (tem farmácia real misturada com supermercado/
  atacarejo — ex. FARMACIA ULTRA ECONOMICA com 289 registros, mais
  volume que "São Paulo" que já era curada). Decisão 100% dele, não
  ativei nenhum. Depois de ativar, rodar `geocodificar_concorrentes`
  pra pegar distância dos novos (só 43 endereços estavam geocodificados
  quando só tinha os 7 curados).
- **Histórico/série temporal** — ~~decisão de arquitetura~~ **tomada
  16/09/26**: tabela `PrecoHistorico`, 1 snapshot/dia, retenção 1 ano
  (ver log acima). Base de dado já rodando sozinha. **Falta só construir
  o gráfico em cima** — aguardando acumular alguns dias/semanas de
  histórico real (hoje só tem o snapshot de 16/09/26) antes de valer a
  pena montar a curva. Quando tiver dado suficiente, entra no mesmo
  painel de detalhe, mesmo padrão SVG da curva de quantidade.
- **Acesso/deploy** — hoje só roda via `manage.py runserver` na máquina
  do Gabriel (`DEBUG=True`, sem host configurado). Se for pra outras
  pessoas do Grupo Velanes acessarem (gerente de loja, comprador),
  precisa decidir hospedagem. Perguntado, sem decisão ainda.

**Manutenção recorrente (não é bug, é rotina):**
- `manage.py geocodificar_concorrentes` **não roda automático** (só
  `vincular_lojas_captacao`/`extrair_bairros_captacao`/
  `descobrir_concorrentes` rodam sozinhos no fim de
  `sincronizar_captacao`) — precisa rodar manual de vez em quando
  conforme aparecem concorrentes novos ATIVADOS na captação (29 de 43
  endereços dos 7 curados originais geocodificados; os 414 descobertos
  em 16/09/26 ainda não foram, só vale a pena depois que Gabriel ativar
  algum deles em Configuração de Concorrentes).
- Cobertura de Ilhéus/Ipiaú ainda crescendo (rodízio por lote do robô
  entrou em produção 15/09/26) — números de comparação nessas 2 cidades
  ainda vão crescer sozinhos, sem precisar de nada daqui. Situação em
  16/09/26: Itabuna 1.000 EANs nossos captados, Ilhéus 35, Ipiaú 8 —
  bem desigual ainda, é o motivo de quase não ter item repetido em mais
  de 1 cidade (só 3 de 1.040 hoje).
