from django.urls import path

from . import views

app_name = "monitor"

urlpatterns = [
    path("", views.monitor_preco, name="monitor_preco"),
    path("sincronizar/", views.sincronizar_agora, name="sincronizar_agora"),
]
