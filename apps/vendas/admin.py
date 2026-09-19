from django.contrib import admin

from .models import AjusteItemMonitoramentoDiario, VendaItem


@admin.register(VendaItem)
class VendaItemAdmin(admin.ModelAdmin):
    list_display = ("ano_mes", "loja", "codigo_erp", "descricao", "itens", "venda", "custo", "lucro")
    list_filter = ("ano_mes", "loja")
    search_fields = ("codigo_erp", "descricao")


@admin.register(AjusteItemMonitoramentoDiario)
class AjusteItemMonitoramentoDiarioAdmin(admin.ModelAdmin):
    list_display = ("ean", "tipo", "categoria", "ativo", "observacao", "criado_em")
    list_filter = ("tipo", "categoria", "ativo")
    search_fields = ("ean", "observacao")
