from django.contrib import admin

from .models import Produto


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("descricao", "ean", "etiqueta", "classificacao", "fabricante",
                     "curva_valor", "preco_venda_atual")
    list_filter = ("classificacao", "curva_valor", "fabricante")
    search_fields = ("descricao", "ean", "etiqueta")
