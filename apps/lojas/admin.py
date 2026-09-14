from django.contrib import admin

from .models import Loja


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = ("nome", "bandeira", "cidade", "bairro", "zona")
    list_filter = ("bandeira", "cidade")
    search_fields = ("nome", "bairro", "endereco", "razao_social")
