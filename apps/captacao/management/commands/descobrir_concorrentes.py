from django.core.management.base import BaseCommand

from apps.captacao.models import PrecoCaptado, Rede


class Command(BaseCommand):
    help = (
        "Cria 1 Rede (tipo=concorrente, INATIVA) pra cada estabelecimento captado "
        "que ainda não bate com nenhuma Rede cadastrada -- antes esses ficavam pra "
        "sempre 'sem rede identificada', fora do radar (Gabriel pediu, 16/09/26: "
        "'não existe isso de curado', quer ver TODO concorrente e escolher quem "
        "conta). Entram inativas de propósito -- revisar/ativar em Configuração de "
        "Concorrentes antes de contarem no Monitor de Preço. Rodar depois de "
        "'sincronizar_captacao' (encadeado automaticamente nele)."
    )

    def handle(self, *args, **options):
        nomes_sem_rede = list(
            PrecoCaptado.objects.filter(rede__isnull=True)
            .exclude(estabelecimento="")
            .values_list("estabelecimento", flat=True)
            .distinct()
        )
        nomes_existentes = set(Rede.objects.values_list("nome", flat=True))

        criadas = 0
        for nome in nomes_sem_rede:
            if nome in nomes_existentes:
                continue
            rede = Rede.objects.create(
                nome=nome, tipo=Rede.TIPO_CONCORRENTE, substrings=[nome], ativa=False,
            )
            PrecoCaptado.objects.filter(estabelecimento=nome, rede__isnull=True).update(rede_id=rede.id)
            nomes_existentes.add(nome)
            criadas += 1

        if criadas:
            self.stdout.write(self.style.SUCCESS(
                f"{criadas} concorrente(s) novo(s) descoberto(s) -- entraram INATIVOS, revisar em "
                f"Configuração de Concorrentes."
            ))
        else:
            self.stdout.write("Nenhum concorrente novo pra descobrir.")
