from django.urls import path

from . import views

app_name = "captacao"

urlpatterns = [
    path("concorrentes/", views.concorrentes, name="concorrentes"),
]
