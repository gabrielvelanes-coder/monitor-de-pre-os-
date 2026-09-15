from django.db import models


class Loja(models.Model):
    """Uma unidade física (Velanes / Ultra Popular). Espelha
    lojas_config.json do robo_cotacao (fonte original do cadastro) —
    importado via `manage.py importar_lojas`, não editado à mão aqui."""

    nome = models.CharField(max_length=50, unique=True)
    codigo = models.CharField(
        max_length=10, blank=True, db_index=True,
        help_text="Código da unidade de negócio no ERP (ex.: '02'), extraído do nome "
                   "'Loja N' -- é como o relatório de vendas identifica a loja "
                   "('Cód. Un. Neg.').",
    )
    bandeira = models.CharField(max_length=30, blank=True)
    cidade = models.CharField(max_length=60, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    zona = models.CharField(max_length=30, blank=True)
    endereco = models.CharField(max_length=200, blank=True)
    razao_social = models.CharField(max_length=200, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    ativa = models.BooleanField(
        default=True,
        help_text="False para loja fechada (ex.: Loja 12/Jaguaquara, fechada -- "
                   "confirmado pelo Gabriel em 2026-09-15). Mantida no cadastro "
                   "por causa do histórico de vendas, mas fora das telas ao vivo.",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"

    def __str__(self):
        return f"{self.nome} ({self.bandeira or 'sem bandeira'} — {self.cidade})"
