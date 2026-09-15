from django.db import models

from apps.lojas.models import Loja


class Rede(models.Model):
    """Uma rede/bandeira que aparece no nome bruto de 'estabelecimento' do
    robô (ex.: 'DROGARIA VELANES', 'RAIA DROGASIL S/A'). `tipo` separa
    nossas duas bandeiras de tudo que é concorrência — usado pra montar o
    Monitor de Preço (nosso preço x preço de cada concorrente). Seed
    inicial vem do concorrentes_config.json do robo_cotacao, mas fica
    editável aqui pelo admin dali pra frente (fonte passa a ser esta)."""

    TIPO_NOSSA = "nossa"
    TIPO_CONCORRENTE = "concorrente"
    TIPO_CHOICES = [(TIPO_NOSSA, "Nossa bandeira"), (TIPO_CONCORRENTE, "Concorrente")]

    nome = models.CharField(max_length=60, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_CONCORRENTE)
    substrings = models.JSONField(
        default=list,
        help_text="Trechos (case-insensitive) que casam contra o nome bruto do estabelecimento.",
    )

    class Meta:
        ordering = ["tipo", "nome"]
        verbose_name = "Rede"
        verbose_name_plural = "Redes"

    def __str__(self):
        return self.nome


class PrecoCaptado(models.Model):
    """1 linha = 1 (produto, estabelecimento, endereço) visto pelo robô no
    Preço da Hora. Espelha a tabela `precos` do `_precos_continuos.sqlite3`
    do robo_cotacao — sincronizado por `manage.py sincronizar_captacao`,
    nunca editado à mão. `cidade_busca` é a cidade que estava ativa na
    busca (Itabuna/Ilhéus/Ipiaú) -- proxy pra região do estabelecimento,
    já que o site só devolve resultados perto da cidade selecionada."""

    ean = models.CharField(max_length=20, db_index=True)
    estabelecimento = models.CharField(max_length=200)
    endereco = models.CharField(max_length=300)
    titulo = models.CharField(max_length=300, blank=True)
    preco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distancia = models.CharField(max_length=30, blank=True)
    termo_origem = models.CharField(max_length=120, blank=True)
    cidade_busca = models.CharField(max_length=60, blank=True, db_index=True)
    atualizado_em = models.DateTimeField()
    rede = models.ForeignKey(
        Rede, null=True, blank=True, on_delete=models.SET_NULL, related_name="precos"
    )
    loja = models.ForeignKey(
        Loja, null=True, blank=True, on_delete=models.SET_NULL, related_name="precos_captados",
        help_text="Só preenchido pra registros de rede='nossa' -- o robô não distingue qual loja "
                   "física é qual, então isso é vinculado depois por heurística de endereço "
                   "(número da rua) em 'manage.py vincular_lojas_captacao', não pelo robô.",
    )
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    bairro = models.CharField(
        max_length=80, blank=True, db_index=True,
        help_text="Extraído do endereço bruto (regex, não vem separado do robô) via "
                   "'manage.py extrair_bairros_captacao' -- pedido do Gabriel pra comparar preço "
                   "do mesmo produto entre bairros da mesma cidade (ex.: bairro X vende mais caro "
                   "que o Centro).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ean", "estabelecimento", "endereco"], name="uniq_preco_captado"
            )
        ]
        indexes = [models.Index(fields=["ean", "cidade_busca"])]
        verbose_name = "Preço captado"
        verbose_name_plural = "Preços captados"

    def __str__(self):
        return f"{self.ean} — {self.estabelecimento} ({self.cidade_busca}): R$ {self.preco}"
