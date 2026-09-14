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
