import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.captacao.models import Rede

NOME_ARQUIVO_PADRAO = "concorrentes_config.json"

# Nossas 2 bandeiras não estão no concorrentes_config.json do robô (ele
# deixa de fora de propósito -- ver comentário do próprio arquivo). Os
# nomes abaixo foram conferidos direto na tabela `precos` do robô
# (2026-09-14): "DROGARIA VELANES" e "DROGARIA ULTRAPOPULAR" (variação
# "DROGARIAS VELANES" também aparece, incluída por segurança).
NOSSAS_REDES = [
    {"nome": "Velanes", "substrings": ["DROGARIA VELANES", "DROGARIAS VELANES"]},
    {"nome": "Ultra Popular", "substrings": ["DROGARIA ULTRAPOPULAR", "ULTRA POPULAR"]},
]


class Command(BaseCommand):
    help = (
        "Semeia/atualiza as Redes (nossas 2 bandeiras + concorrentes) a partir do "
        "concorrentes_config.json do robo_cotacao. Rodar 1x pra popular; dali em "
        "diante, editar direto no admin daqui (não precisa rodar de novo, exceto "
        "pra puxar concorrente NOVO cadastrado só no arquivo do robô)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", default=None, help="Caminho do concorrentes_config.json")

    def handle(self, *args, **options):
        criadas, atualizadas = 0, 0

        for r in NOSSAS_REDES:
            _, created = Rede.objects.update_or_create(
                nome=r["nome"],
                defaults={"tipo": Rede.TIPO_NOSSA, "substrings": r["substrings"]},
            )
            criadas += created
            atualizadas += not created

        caminho = Path(options["arquivo"]) if options["arquivo"] else None
        if caminho is None:
            from django.conf import settings

            candidato = settings.DADOS_ENTRADA / NOME_ARQUIVO_PADRAO
            caminho = candidato if candidato.exists() else None

        if caminho is None:
            self.stdout.write(self.style.WARNING(
                f"'{NOME_ARQUIVO_PADRAO}' não encontrado em dados/entrada/ -- só as 2 bandeiras "
                f"próprias foram semeadas. Copie o arquivo do robo_cotacao (ou passe --arquivo) "
                f"pra trazer os concorrentes."
            ))
        else:
            with open(caminho, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            for c in cfg.get("concorrentes", []):
                _, created = Rede.objects.update_or_create(
                    nome=c["nome"],
                    defaults={"tipo": Rede.TIPO_CONCORRENTE, "substrings": c["substrings"]},
                )
                criadas += created
                atualizadas += not created

            indiana_substrings = cfg.get("indiana_substrings")
            if indiana_substrings:
                _, created = Rede.objects.update_or_create(
                    nome="Farmácia Indiana",
                    defaults={"tipo": Rede.TIPO_CONCORRENTE, "substrings": indiana_substrings},
                )
                criadas += created
                atualizadas += not created

        self.stdout.write(self.style.SUCCESS(f"{criadas} rede(s) criada(s), {atualizadas} atualizada(s)."))
