from django.contrib import admin

from .models import VendaItem


@admin.register(VendaItem)
class VendaItemAdmin(admin.ModelAdmin):
    list_display = ("ano_mes", "loja", "codigo_erp", "descricao", "itens", "venda", "custo", "lucro")
    list_filter = ("ano_mes", "loja")
    search_fields = ("codigo_erp", "descricao")
