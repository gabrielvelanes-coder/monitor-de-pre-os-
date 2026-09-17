from django.urls import path

from . import views

app_name = "vendas"

urlpatterns = [
    path("relevancia/", views.relevancia, name="relevancia"),
    path("custo-margem/", views.custo_margem, name="custo_margem"),
    path("itens-relevantes/", views.selecao_itens_relevantes, name="selecao_itens_relevantes"),
]
