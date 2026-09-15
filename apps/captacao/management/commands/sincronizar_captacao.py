import sqlite3
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.captacao.models import PrecoCaptado, Rede
from apps.captacao.utils import identificar_rede, parse_preco_brl


class Command(BaseCommand):
    help = (
        "Sincroniza a base local (PrecoCaptado) com o _precos_continuos.sqlite3 do "
        "robo_cotacao -- lê de lá (somente leitura, nunca escreve no banco do robô) "
        "e faz upsert aqui. Rodar sob demanda ou agendado (ex.: a cada 30min, junto "
        "com o agendador do robô)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--arquivo", default=None,
            help="Caminho do _precos_continuos.sqlite3 (default: settings.CAMINHO_DB_ROBO_COTACAO)",
        )

    def handle(self, *args, **options):
        caminho = options["arquivo"] or str(settings.CAMINHO_DB_ROBO_COTACAO)
        if not options["arquivo"] and not settings.CAMINHO_DB_ROBO_COTACAO.exists():
            raise CommandError(
                f"Não encontrei o banco do robô em '{caminho}'. Confira "
                f"settings.CAMINHO_DB_ROBO_COTACAO ou passe --arquivo."
            )

        # mode=ro: nunca escreve nem cria lock de escrita no banco do robô,
        # que pode estar sendo escrito pelo agendador ao mesmo tempo.
        uri = f"file:{caminho}?mode=ro"
        try:
            origem = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as exc:
            raise CommandError(f"Não consegui abrir '{caminho}' somente-leitura: {exc}")

        redes_cache = [(r.id, r.substrings) for r in Rede.objects.all()]
        if not redes_cache:
            self.stdout.write(self.style.WARNING(
                "Nenhuma Rede cadastrada ainda -- rode 'manage.py seed_redes' primeiro pra "
                "classificar nosso preço x concorrência. Sincronizando sem classificação por ora."
            ))

        cursor = origem.execute(
            "SELECT ean, estabelecimento, endereco, titulo, preco, distancia, "
            "termo_origem, atualizado_em, cidade_busca FROM precos"
        )

        objetos = []
        for ean, estabelecimento, endereco, titulo, preco, distancia, termo, atualizado_em, cidade in cursor:
            try:
                dt = datetime.fromisoformat(atualizado_em)
            except (TypeError, ValueError):
                dt = timezone.now()
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)

            objetos.append(PrecoCaptado(
                ean=ean, estabelecimento=estabelecimento, endereco=endereco,
                titulo=titulo or "", preco=parse_preco_brl(preco), distancia=distancia or "",
                termo_origem=termo or "", cidade_busca=cidade or "", atualizado_em=dt,
                rede_id=identificar_rede(estabelecimento, redes_cache),
            ))
        origem.close()

        if not objetos:
            self.stdout.write(self.style.WARNING("Base do robô está vazia -- nada pra sincronizar."))
            return

        PrecoCaptado.objects.bulk_create(
            objetos,
            update_conflicts=True,
            unique_fields=["ean", "estabelecimento", "endereco"],
            update_fields=["titulo", "preco", "distancia", "termo_origem",
                            "cidade_busca", "atualizado_em", "rede_id"],
            batch_size=1000,
        )
        sem_rede = sum(1 for o in objetos if o.rede_id is None)
        self.stdout.write(self.style.SUCCESS(f"{len(objetos)} preço(s) sincronizado(s)."))
        if sem_rede:
            self.stdout.write(self.style.WARNING(
                f"{sem_rede} sem rede identificada (estabelecimento não bate com nenhum "
                f"substring cadastrado) -- normal ter uma cauda de mercados/farmácias avulsas "
                f"fora do radar; revisar no admin se o número parecer alto."
            ))

        call_command("vincular_lojas_captacao")
