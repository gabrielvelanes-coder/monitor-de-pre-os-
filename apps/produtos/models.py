from django.db import models


class Produto(models.Model):
    """Cadastro cruzado de 2 relatórios do ERP (cadastro base de estoque +
    árvore mercadológica) -- `manage.py importar_produtos`. `ean` é o
    Código de Barras real quando o produto tem um cadastrado; `etiqueta` é
    o código interno usado quando não tem (a mesma lógica de "~5% sem EAN"
    já vista nos outros painéis). O relatório de vendas identifica o item
    por QUALQUER um dos dois em 'Cód. Barras/Etiq.' -- ver
    `apps.vendas.utils.chaves_possiveis`."""

    ean = models.CharField(max_length=20, blank=True, db_index=True)
    etiqueta = models.CharField(max_length=20, blank=True, db_index=True)
    descricao = models.CharField(max_length=250, blank=True)
    fabricante = models.CharField(max_length=120, blank=True)

    # "ARVORE NOVA > PROPAGADO > OTC/MIP" (árvore mercadológica completa,
    # como vem do cadastro) + o nível logo abaixo de "ARVORE NOVA" já
    # separado (usado como agrupador de relevância -- "Classificação" no
    # sentido que o Gabriel pediu).
    classificacao_completa = models.CharField(max_length=250, blank=True)
    classificacao = models.CharField(max_length=120, blank=True, db_index=True)

    curva_valor = models.CharField(max_length=2, blank=True)
    curva_qtd = models.CharField(max_length=2, blank=True)

    preco_venda_atual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preco_referencial = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["descricao"]
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"

    def __str__(self):
        return f"{self.ean or self.etiqueta} — {self.descricao}"
