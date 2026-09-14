import glob
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.lojas.models import Loja
from apps.produtos.models import Produto
from apps.produtos.utils import chaves_possiveis, parse_decimal
from apps.vendas.models import VendaItem

PADRAO_ARQUIVO = "vendas *.xls"

# Posição das colunas no relatório "Análise de Venda por Item" (header na
# linha 1, linha 0 é o título/período) -- por POSIÇÃO, não pelo nome, porque
# a coluna '%' se repete 3x (Desconto/Custo/Lucro) e o pandas sufixa cada
# uma diferente (%, %.1, %.2) de um jeito que não vale a pena confiar.
COL_LOJA, COL_ANOMES, COL_CODIGO, COL_DESCRICAO, COL_ITENS, COL_VENDA = 0, 1, 2, 3, 4, 5
COL_DESCONTO, COL_CUSTO, COL_LUCRO = 7, 9, 11


class Command(BaseCommand):
    help = (
        "Importa os relatórios mensais 'vendas <mês>.xls' (Análise de Venda por Item, "
        "COM loja e mês -- diferente do relatório anual consolidado). Cada arquivo tem "
        "2 abas (limite de 65.536 linhas do .xls)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", action="append", default=None,
                             help="Caminho de 1 arquivo específico (repetível). Default: todos "
                                  f"os '{PADRAO_ARQUIVO}' em dados/entrada/.")

    @transaction.atomic
    def handle(self, *args, **options):
        arquivos = options["arquivo"] or sorted(glob.glob(str(settings.DADOS_ENTRADA / PADRAO_ARQUIVO)))
        if not arquivos:
            raise CommandError(f"Nenhum arquivo '{PADRAO_ARQUIVO}' em dados/entrada/.")

        lojas_por_codigo = {l.codigo: l.id for l in Loja.objects.exclude(codigo="")}
        if not lojas_por_codigo:
            raise CommandError("Nenhuma Loja com código -- rode 'manage.py importar_lojas' primeiro.")

        produto_por_chave: dict[str, int] = {}
        for p in Produto.objects.all():
            for chave in chaves_possiveis(p.ean) | chaves_possiveis(p.etiqueta):
                produto_por_chave.setdefault(chave, p.id)

        total_linhas = 0
        sem_loja: set[str] = set()
        sem_produto = 0

        for caminho in arquivos:
            self.stdout.write(f"Lendo {Path(caminho).name}...")
            planilhas = pd.ExcelFile(caminho).sheet_names
            for aba in planilhas:
                df = pd.read_excel(caminho, sheet_name=aba, header=1)
                objetos = []
                for row in df.itertuples(index=False, name=None):
                    cod_loja = str(row[COL_LOJA]).strip().zfill(2)
                    loja_id = lojas_por_codigo.get(cod_loja)
                    if loja_id is None:
                        sem_loja.add(cod_loja)
                        continue

                    codigo_erp = str(row[COL_CODIGO]).strip()
                    if codigo_erp.endswith(".0"):
                        codigo_erp = codigo_erp[:-2]
                    ano_mes = str(row[COL_ANOMES]).strip()

                    produto_id = None
                    for chave in chaves_possiveis(codigo_erp):
                        if chave in produto_por_chave:
                            produto_id = produto_por_chave[chave]
                            break
                    if produto_id is None:
                        sem_produto += 1

                    objetos.append(VendaItem(
                        loja_id=loja_id, produto_id=produto_id, codigo_erp=codigo_erp,
                        descricao=str(row[COL_DESCRICAO] or "").strip(), ano_mes=ano_mes,
                        itens=parse_decimal(row[COL_ITENS]) or 0,
                        venda=parse_decimal(row[COL_VENDA]) or 0,
                        desconto=parse_decimal(row[COL_DESCONTO]) or 0,
                        custo=parse_decimal(row[COL_CUSTO]) or 0,
                        lucro=parse_decimal(row[COL_LUCRO]) or 0,
                    ))

                VendaItem.objects.bulk_create(
                    objetos, update_conflicts=True,
                    unique_fields=["loja", "codigo_erp", "ano_mes"],
                    update_fields=["produto", "descricao", "itens", "venda", "desconto", "custo", "lucro"],
                    batch_size=2000,
                )
                total_linhas += len(objetos)
                self.stdout.write(f"  {aba}: {len(objetos)} linha(s).")

        self.stdout.write(self.style.SUCCESS(f"{total_linhas} linha(s) de venda importada(s)."))
        if sem_loja:
            self.stdout.write(self.style.WARNING(
                f"Código(s) de loja não cadastrado(s), ignorado(s): {sorted(sem_loja)}"
            ))
        if sem_produto:
            self.stdout.write(self.style.WARNING(
                f"{sem_produto} linha(s) sem Produto correspondente (venda ainda importada, "
                f"só fica sem classificação/EAN até o cadastro ser completado)."
            ))
