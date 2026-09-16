from django.contrib import admin

from .models import PrecoCaptado, Rede


@admin.register(Rede)
class RedeAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "ativa", "substrings")
    list_filter = ("tipo", "ativa")
    list_editable = ("ativa",)


@admin.register(PrecoCaptado)
class PrecoCaptadoAdmin(admin.ModelAdmin):
    list_display = ("ean", "estabelecimento", "rede", "cidade_busca", "preco", "atualizado_em")
    list_filter = ("cidade_busca", "rede")
    search_fields = ("ean", "estabelecimento", "titulo")
    date_hierarchy = "atualizado_em"
