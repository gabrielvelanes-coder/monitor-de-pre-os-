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


class PrecoHistorico(models.Model):
    """1 snapshot por dia de cada `PrecoCaptado` -- criado porque
    `PrecoCaptado` SOBRESCREVE (chave única ean+estabelecimento+endereço,
    cada sincronização faz update na mesma linha), então o preço de ontem
    já não existe em lugar nenhum hoje. Gabriel pediu (16/09/26) pra
    guardar histórico pra poder ver evolução de preço no tempo -- decisão
    dele: 1 snapshot por DIA (não por sincronização, que roda a cada
    30min -- viraria milhões de linhas por semana sem necessidade
    nenhuma), retenção de 1 ano (apagado pelo próprio
    `snapshot_precos_historico` a cada rodada). Alimentado por
    `manage.py snapshot_precos_historico`, rodando 1x/dia via Tarefa
    Agendada (mesmo padrão de `sincronizar_captacao`)."""

    data = models.DateField(db_index=True)
    ean = models.CharField(max_length=20, db_index=True)
    cidade_busca = models.CharField(max_length=60, blank=True, db_index=True)
    tipo = models.CharField(max_length=20, blank=True)  # "nossa"/"concorrente" no momento do snapshot
    rede_nome = models.CharField(max_length=60, blank=True)
    estabelecimento = models.CharField(max_length=200, blank=True)
    endereco = models.CharField(max_length=300, blank=True)
    loja = models.ForeignKey(
        Loja, null=True, blank=True, on_delete=models.SET_NULL, related_name="precos_historico"
    )
    preco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["data", "ean", "estabelecimento", "endereco"], name="uniq_preco_historico"
            )
        ]
        indexes = [models.Index(fields=["ean", "cidade_busca", "data"])]
        verbose_name = "Preço histórico"
        verbose_name_plural = "Preços históricos"

    def __str__(self):
        return f"{self.data} — {self.ean} — {self.estabelecimento}: R$ {self.preco}"
