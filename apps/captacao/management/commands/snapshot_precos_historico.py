from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.captacao.models import PrecoCaptado, PrecoHistorico

RETENCAO_DIAS = 365


class Command(BaseCommand):
    help = (
        "Grava 1 snapshot do dia de todo PrecoCaptado (que sobrescreve, não guarda "
        "histórico) em PrecoHistorico -- pra dar base ao gráfico de evolução de preço "
        "no tempo. Rodar 1x/dia via Tarefa Agendada, depois de sincronizar_captacao "
        "já ter atualizado os preços do dia. Idempotente: rodar 2x no mesmo dia não "
        "duplica (ignora conflito na chave única data+ean+estabelecimento+endereço)."
    )

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        antes = PrecoHistorico.objects.filter(data=hoje).count()

        registros = [
            PrecoHistorico(
                data=hoje,
                ean=p.ean,
                cidade_busca=p.cidade_busca,
                tipo=p.rede.tipo if p.rede else "",
                rede_nome=p.rede.nome if p.rede else "",
                estabelecimento=p.estabelecimento,
                endereco=p.endereco,
                loja_id=p.loja_id,
                preco=p.preco,
            )
            for p in PrecoCaptado.objects.exclude(preco__isnull=True).select_related("rede")
        ]
        # ignore_conflicts=True faz o bulk_create sempre "retornar" a lista
        # inteira que foi passada, mesmo pros que colidiram com a chave
        # única e não foram inseridos de verdade -- por isso conta
        # antes/depois em vez de confiar no retorno do bulk_create.
        PrecoHistorico.objects.bulk_create(registros, ignore_conflicts=True)
        depois = PrecoHistorico.objects.filter(data=hoje).count()
        self.stdout.write(f"{depois - antes} snapshot(s) novo(s) gravado(s) pra {hoje} ({depois} no total do dia).")

        limite = hoje - timedelta(days=RETENCAO_DIAS)
        apagados, _ = PrecoHistorico.objects.filter(data__lt=limite).delete()
        if apagados:
            self.stdout.write(f"{apagados} registro(s) de mais de {RETENCAO_DIAS} dias apagado(s) (retenção).")
