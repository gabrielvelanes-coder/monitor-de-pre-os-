from django.urls import path

from . import views

app_name = "monitor"

urlpatterns = [
    path("", views.monitor_preco, name="monitor_preco"),
]
