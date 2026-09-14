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

`cidade_busca` (nova coluna no robô, adicionada 2026-09-14) é a cidade que
estava ativa na busca (Itabuna/Ilhéus/Ipiaú) — usada aqui como proxy de
região, já que o Preço da Hora só devolve resultados perto da cidade
selecionada.

## Dados de entrada (`dados/entrada/`, gitignored)

- `lojas_config.json` / `concorrentes_config.json` — cópias do robo_cotacao,
  reimportar quando o Gabriel atualizar lá.
- **Pendente:** relatório "Análise de Venda por Item" **por loja** (ou por
  bandeira) — o que ele mandou (`vendas por item 2026.xls`) é da rede
  inteira, sem quebra, não dá pra separar por bandeira/cidade. Precisa do
  mesmo relatório recortado por loja, como nos outros painéis.
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
- Sem tela de Custo x Margem nem Análise de Entradas ainda — dependem do
  relatório por loja e do relatório de entrada (ver pendências acima).
- Sem motor de relevância ("quais itens mais importam") — pendente definir
  a regra com o Gabriel (curva ABC? giro? categoria estratégica?).
