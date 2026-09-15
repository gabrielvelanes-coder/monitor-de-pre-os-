import re

from django.core.management.base import BaseCommand

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja

_REGEX_NUMERO = re.compile(r"\d+")


def _numero_rua(endereco: str) -> str | None:
    """Primeiro número que aparece no endereço -- é o número do imóvel na
    maioria dos formatos vistos (robô e cadastro de lojas), mesmo com
    abreviação/pontuação diferentes ('AV CINQUENTENÁRIO, 639 CENTRO' vs
    'AVENIDA CINQUENTENARIO 639 CENTRO 45600004, ITABUNA')."""
    m = _REGEX_NUMERO.search(endereco or "")
    return m.group() if m else None


class Command(BaseCommand):
    help = (
        "Vincula cada PrecoCaptado de rede='nossa' a uma Loja específica, por "
        "heurística de endereço (número da rua) -- o robô só sabe a bandeira "
        "('DROGARIA VELANES'/'DROGARIA ULTRAPOPULAR'), não qual loja física. "
        "Best-effort: só vincula quando há exatamente 1 Loja candidata (mesma "
        "bandeira/cidade, mesmo número de rua); ambíguo ou sem candidata fica "
        "sem vínculo. Rodar depois de 'sincronizar_captacao' (ou via ele)."
    )

    def handle(self, *args, **options):
        pendentes = PrecoCaptado.objects.filter(rede__tipo="nossa", loja__isnull=True).select_related("rede")

        lojas_por_bandeira_cidade: dict[tuple[str, str], list[Loja]] = {}
        for loja in Loja.objects.exclude(bandeira="").exclude(cidade=""):
            lojas_por_bandeira_cidade.setdefault((loja.bandeira, loja.cidade), []).append(loja)

        vinculados, ambiguos, sem_candidata, sem_numero = 0, 0, 0, 0
        for p in pendentes.iterator():
            numero = _numero_rua(p.endereco)
            if not numero:
                sem_numero += 1
                continue
            candidatas = lojas_por_bandeira_cidade.get((p.rede.nome, p.cidade_busca), [])
            bateram = [l for l in candidatas if numero in (l.endereco or "")]
            if len(bateram) == 1:
                p.loja = bateram[0]
                p.save(update_fields=["loja"])
                vinculados += 1
            elif len(bateram) > 1:
                ambiguos += 1
            else:
                sem_candidata += 1

        total = vinculados + ambiguos + sem_candidata + sem_numero
        self.stdout.write(self.style.SUCCESS(f"{vinculados} de {total} registro(s) vinculado(s) a uma loja."))
        if ambiguos or sem_candidata or sem_numero:
            self.stdout.write(self.style.WARNING(
                f"Sem vínculo: {ambiguos} ambíguo(s) (mais de 1 loja com o mesmo número), "
                f"{sem_candidata} sem loja candidata (bandeira/cidade sem cadastro batendo), "
                f"{sem_numero} sem número identificável no endereço."
            ))
