import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.lojas.models import Loja

NOME_ARQUIVO_PADRAO = "lojas_config.json"


class Command(BaseCommand):
    help = (
        "Importa/atualiza o cadastro de lojas a partir de lojas_config.json "
        "(mesmo arquivo usado pelo robo_cotacao — fonte única do mapa de "
        "lojas, pra não duplicar cadastro em 2 lugares). Por padrão procura "
        f"em dados/entrada/{NOME_ARQUIVO_PADRAO}; passe --arquivo pra usar outro caminho."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", default=None, help="Caminho do lojas_config.json")

    def handle(self, *args, **options):
        caminho = Path(options["arquivo"]) if options["arquivo"] else settings.DADOS_ENTRADA / NOME_ARQUIVO_PADRAO
        if not caminho.exists():
            raise CommandError(
                f"Não encontrei '{caminho}'. Copie o lojas_config.json do robo_cotacao pra "
                f"dados/entrada/ (ou passe --arquivo <caminho>)."
            )

        with open(caminho, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        criadas, atualizadas = 0, 0
        for l in cfg.get("lojas", []):
            digitos = "".join(ch for ch in l["nome"] if ch.isdigit())
            codigo = digitos.zfill(2) if digitos else ""
            _, created = Loja.objects.update_or_create(
                nome=l["nome"],
                defaults={
                    "codigo": codigo,
                    "bandeira": l.get("bandeira") or "",
                    "cidade": l.get("cidade") or "",
                    "bairro": l.get("bairro") or "",
                    "zona": l.get("zona") or "",
                    "endereco": l.get("endereco") or "",
                    "razao_social": l.get("razao_social") or "",
                    "lat": l.get("lat"),
                    "lon": l.get("lon"),
                },
            )
            criadas += created
            atualizadas += not created

        sem_bandeira = Loja.objects.filter(bandeira="").count()
        self.stdout.write(self.style.SUCCESS(
            f"{criadas} loja(s) criada(s), {atualizadas} atualizada(s)."
        ))
        if sem_bandeira:
            self.stdout.write(self.style.WARNING(
                f"{sem_bandeira} loja(s) sem bandeira — confira no admin."
            ))
