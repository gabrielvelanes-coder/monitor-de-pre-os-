import re
import unicodedata

from django.core.management.base import BaseCommand

from apps.captacao.models import PrecoCaptado

# O robô não guarda bairro separado, só o endereço bruto no formato
# "[RUA] [NÚMERO] [BAIRRO] [CEP], [CIDADE]" (ex.: "AVENIDA CINQUENTENARIO
# 668 CENTRO 45600004, ITABUNA"). Testado contra 492 endereços únicos
# reais (15/09/26): 489 (99,4%) batem com número normal + BAIRRO + CEP de
# 8 dígitos; o pedaço "(?:\d+[-A-Z]?|S/?N)" cobre número comum ("668"),
# número com sufixo ("428A"/"140-A") e "S/N" (sem número).
_REGEX_BAIRRO = re.compile(r"(?:\d+[-A-Z]?|S/?N)\s+(.+?)\s+\d{8},")


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _extrair_bairro(endereco: str) -> str:
    """BUG REAL encontrado 15/09/26: o mesmo bairro aparece grafado com e
    sem acento em capturas diferentes do robô (ex.: 'SAO CAETANO' 1287x,
    'SÃO CAETANO' 229x) -- provável inconsistência do próprio HTML do
    Preço da Hora entre passadas. Sem normalizar, o filtro de bairro
    fragmenta o mesmo lugar em 2+ opções no dropdown. Tira acento sempre
    (mantém maiúsculo, que já é o padrão do endereço bruto).

    2º BUG REAL encontrado (mesma investigação): uma minoria de endereços
    (58 de 10.428, quase todos concorrente fora de Itabuna/Ilhéus/Ipiaú,
    ex. Salvador) usa formato de CEP com faixa de numeração ("...DE 1 A
    881...") que engana o regex e vaza número pro meio do bairro
    capturado (ex. '1263 S CAETANO', 'ATE 881 431 CENTRO'). Bairro de
    verdade não tem dígito -- rejeita a captura nesse caso (fica vazio,
    mesmo tratamento de "não bateu o padrão", não quebra nada)."""
    m = _REGEX_BAIRRO.search(endereco or "")
    if not m:
        return ""
    bairro = _sem_acento(m.group(1).strip())
    return bairro if not re.search(r"\d", bairro) else ""


class Command(BaseCommand):
    help = (
        "Extrai o bairro do endereço bruto captado (regex, não vem separado do robô) -- "
        "pedido do Gabriel pra comparar preço do mesmo produto entre bairros da mesma "
        "cidade. Rodar depois de 'sincronizar_captacao' (ou via ele)."
    )

    def handle(self, *args, **options):
        pendentes = PrecoCaptado.objects.filter(bairro="")
        total = pendentes.count()
        extraidos, sem_match = 0, 0
        for p in pendentes.iterator():
            bairro = _extrair_bairro(p.endereco)
            if bairro:
                p.bairro = bairro
                p.save(update_fields=["bairro"])
                extraidos += 1
            else:
                sem_match += 1

        self.stdout.write(self.style.SUCCESS(f"{extraidos} de {total} bairro(s) extraído(s)."))
        if sem_match:
            self.stdout.write(self.style.WARNING(
                f"{sem_match} endereço(s) não bateram com o padrão esperado (formato diferente "
                f"do usual) -- ficam sem bairro, sem quebrar a tela."
            ))
