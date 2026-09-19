from django.db import models

from apps.lojas.models import Loja
from apps.produtos.models import Produto


class VendaItem(models.Model):
    """1 linha do relatório 'Análise de Venda por Item' (por loja/mês) do
    ERP -- `manage.py importar_vendas`. `produto` fica null quando o
    código do relatório não bateu com nenhum Produto conhecido (cadastro
    incompleto ou item descontinuado); guardamos `codigo_erp`/`descricao`
    mesmo assim, pra não perder o dado."""

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="vendas")
    produto = models.ForeignKey(Produto, null=True, blank=True, on_delete=models.SET_NULL, related_name="vendas")
    codigo_erp = models.CharField(max_length=20, db_index=True)
    descricao = models.CharField(max_length=250, blank=True)
    ano_mes = models.CharField(max_length=7, db_index=True)  # "2026-01"

    itens = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    venda = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    custo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    lucro = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["loja", "codigo_erp", "ano_mes"], name="uniq_venda_item")
        ]
        indexes = [models.Index(fields=["ano_mes", "loja"])]
        verbose_name = "Venda de item"
        verbose_name_plural = "Vendas de item"

    def __str__(self):
        return f"{self.loja} — {self.codigo_erp} ({self.ano_mes})"


class SelecaoItemRelevante(models.Model):
    """Gabriel escolhe, dentro dos candidatos sugeridos (Top faturamento +
    Top unidades, ver `services.itens_relevantes`), quais itens realmente
    quer acompanhar de preço todo dia -- ver tela "Selecionar Itens
    Relevantes" (17/09/26, pedido explícito: "você identifica quais itens
    são mais relevantes e eu escolho quais quero olhar"). `ean` (não FK
    pra Produto) pra ficar independente de recadastro/troca de Produto,
    igual `PrecoCaptado.ean`. Sem registro = ainda não decidido, conta
    como selecionado por padrão (candidato sugerido já é relevante até
    prova em contrário)."""

    ean = models.CharField(max_length=20, unique=True, db_index=True)
    selecionado = models.BooleanField(default=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Seleção de item relevante"
        verbose_name_plural = "Seleções de itens relevantes"

    def __str__(self):
        return f"{self.ean} ({'selecionado' if self.selecionado else 'ignorado'})"


class AjusteItemMonitoramentoDiario(models.Model):
    """Ajuste manual do Gabriel por cima da lista automática (top de unidades
    por categoria) de `services.itens_monitoramento_diario` -- pedido
    19/09/26: ele quer trocar itens específicos por outros de sua escolha,
    não só aceitar o ranking automático. EXCLUIR tira o EAN da lista (a vaga
    da categoria NÃO é reposta automaticamente pelo próximo do ranking --
    encolhe a categoria de propósito, pra não trazer de volta um item
    parecido escolhido por acaso). INCLUIR força o EAN a entrar na
    `categoria` indicada, além das vagas automáticas (pode fazer a categoria
    passar do tamanho padrão)."""

    EXCLUIR = "EXCLUIR"
    INCLUIR = "INCLUIR"
    TIPO_CHOICES = [(EXCLUIR, "Excluir"), (INCLUIR, "Incluir")]

    ean = models.CharField(max_length=20, db_index=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    categoria = models.CharField(
        max_length=40, blank=True,
        help_text="Obrigatório pra INCLUIR (nome exato da categoria, ex. 'Propagado'). Ignorado em EXCLUIR.",
    )
    observacao = models.CharField(max_length=200, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ajuste manual (monitoramento diário)"
        verbose_name_plural = "Ajustes manuais (monitoramento diário)"

    def __str__(self):
        return f"{self.tipo} {self.ean} ({self.categoria or '-'})"
