import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.vendas.services import itens_relevantes


class Command(BaseCommand):
    help = (
        "Exporta o Top N por faturamento + Top N por unidades (união, dedup por EAN) "
        "pra _itens_relevantes.json na pasta do robo_cotacao -- roda `termos_prioritarios.py` "
        "lá depois pra gerar os termos de busca. Rodar sob demanda, sempre que vendas novas "
        "forem importadas (não precisa ser diário)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--top-n", type=int, default=100,
            help="Quantos itens pegar de cada métrica antes de unir (padrão: 100).",
        )

    def handle(self, *args, **options):
        top_n = options["top_n"]
        itens = itens_relevantes(top_n=top_n)

        caminho = settings.CAMINHO_ITENS_RELEVANTES_ROBO_COTACAO
        caminho.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "top_n_por_metrica": top_n,
            "itens": [
                {
                    "ean": i["ean"],
                    "descricao": i["descricao"],
                    "venda": float(i["venda"]),
                    "itens": float(i["itens"]),
                    "origem": i["origem"],
                }
                for i in itens
            ],
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        n_ambos = sum(1 for i in itens if i["origem"] == "ambos")
        n_faturamento = sum(1 for i in itens if i["origem"] == "faturamento")
        n_unidades = sum(1 for i in itens if i["origem"] == "unidades")
        self.stdout.write(self.style.SUCCESS(
            f"{len(itens)} itens relevantes exportados pra {caminho} "
            f"({n_faturamento} só faturamento, {n_unidades} só unidades, {n_ambos} nos dois)."
        ))
