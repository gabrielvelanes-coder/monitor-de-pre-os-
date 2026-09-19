import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.vendas.services import itens_monitoramento_diario


class Command(BaseCommand):
    help = (
        "Exporta a lista FIXA de 35 itens do monitoramento diário de preço "
        "(10 Genéricos + 5 Similares + 5 Propagados + 5 Fraldas + 4 Leites + 4 resto de "
        "Mundo Infantil + 2 top geral, por unidades vendidas) pra "
        "_itens_monitoramento_diario.json na pasta do robo_cotacao -- rodar "
        "'termos_diarios.py' lá depois pra gerar os termos de busca. Rodar sob demanda, "
        "sempre que vendas novas forem importadas (não precisa ser diário)."
    )

    def handle(self, *args, **options):
        itens = itens_monitoramento_diario()

        caminho = settings.CAMINHO_ITENS_MONITORAMENTO_DIARIO_ROBO_COTACAO
        caminho.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "itens": [
                {
                    "ean": i["ean"],
                    "descricao": i["descricao"],
                    "categoria": i["categoria"],
                    "venda": float(i["venda"]),
                    "itens": float(i["itens"]),
                }
                for i in itens
            ],
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(f"{len(itens)} item(ns) exportados pra {caminho}:"))
        por_categoria: dict[str, int] = {}
        for i in itens:
            por_categoria[i["categoria"]] = por_categoria.get(i["categoria"], 0) + 1
        for categoria, n in por_categoria.items():
            self.stdout.write(f"  {categoria}: {n}")
