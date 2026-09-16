import glob
import unicodedata
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.lojas.models import Loja
from apps.produtos.models import Produto
from apps.produtos.utils import chaves_possiveis, parse_decimal
from apps.vendas.models import VendaItem

PADRAO_ARQUIVO = "vendas *.xls"

# BUG REAL encontrado 16/09/26: até aqui a posição das colunas era fixa
# (0=Loja, 1=Ano-mês, ...) -- funcionou em jan/fev/mar/abr/jul, mas o
# arquivo de maio reenviado veio com Loja e Ano-mês TROCADOS de posição
# (mesmo nome de coluna, ordem diferente -- o ERP não exporta sempre na
# mesma ordem). Se importasse por posição sem conferir, "2026-05" vinha
# lido como código de loja. Corrigido: detecta a posição de cada coluna
# pelo NOME (Ano-mês/Cód. Un. Neg./etc. são únicos -- só as 3 colunas
# "%" repetidas, que a gente nem usa, são ambíguas). A 2ª aba de cada
# arquivo não tem cabeçalho de texto (é uma continuação por causa do
# limite de 65.536 linhas do .xls) -- reaproveita a mesma posição
# detectada na 1ª aba, assumindo mesma ordem de coluna dentro do mesmo
# arquivo (validado: sempre foi assim nos arquivos vistos até agora).
_COLUNAS_ESPERADAS = {
    "loja": "cod. un. neg.",
    "ano_mes": "ano-mes",
    "codigo": "cod. barras/etiq.",
    "descricao": "embalagem",
    "itens": "itens",
    "venda": "venda",
    "desconto": "desconto",
    "custo": "custo",
    "lucro": "lucro",
}


def _sem_acento(s) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def _mapear_colunas(colunas) -> dict[str, int]:
    normalizadas = {_sem_acento(c): i for i, c in enumerate(colunas)}
    mapa, faltando = {}, []
    for chave, nome in _COLUNAS_ESPERADAS.items():
        idx = normalizadas.get(nome)
        if idx is None:
            faltando.append(nome)
        mapa[chave] = idx
    if faltando:
        raise CommandError(
            f"Não achei a(s) coluna(s) {faltando} no relatório -- formato diferente do "
            f"esperado, confira antes de importar (colunas encontradas: {list(colunas)})."
        )
    return mapa


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
            mapa_colunas: dict[str, int] | None = None
            for aba in planilhas:
                df = pd.read_excel(caminho, sheet_name=aba, header=1)
                if mapa_colunas is None:
                    # só a 1ª aba do arquivo tem cabeçalho de texto de
                    # verdade -- a 2ª é continuação sem header (ver
                    # comentário no topo do arquivo), reaproveita a mesma
                    # posição detectada aqui.
                    mapa_colunas = _mapear_colunas(df.columns)
                c = mapa_colunas
                objetos = []
                for row in df.itertuples(index=False, name=None):
                    # BUG REAL encontrado 16/09/26: quando o arquivo tem
                    # alguma linha em branco/total na coluna de loja, o
                    # pandas lê a coluna inteira como float (não dá pra
                    # ter NaN num int) -- "22" vira "22.0", nunca bate com
                    # o código cadastrado (2 dígitos). Mesmo tratamento
                    # que já existia pro código de barras/etiqueta.
                    cod_loja_bruto = str(row[c["loja"]]).strip()
                    if cod_loja_bruto.endswith(".0"):
                        cod_loja_bruto = cod_loja_bruto[:-2]
                    cod_loja = cod_loja_bruto.zfill(2)
                    loja_id = lojas_por_codigo.get(cod_loja)
                    if loja_id is None:
                        sem_loja.add(cod_loja)
                        continue

                    codigo_erp = str(row[c["codigo"]]).strip()
                    if codigo_erp.endswith(".0"):
                        codigo_erp = codigo_erp[:-2]
                    ano_mes = str(row[c["ano_mes"]]).strip()

                    produto_id = None
                    for chave in chaves_possiveis(codigo_erp):
                        if chave in produto_por_chave:
                            produto_id = produto_por_chave[chave]
                            break
                    if produto_id is None:
                        sem_produto += 1

                    objetos.append(VendaItem(
                        loja_id=loja_id, produto_id=produto_id, codigo_erp=codigo_erp,
                        descricao=str(row[c["descricao"]] or "").strip(), ano_mes=ano_mes,
                        itens=parse_decimal(row[c["itens"]]) or 0,
                        venda=parse_decimal(row[c["venda"]]) or 0,
                        desconto=parse_decimal(row[c["desconto"]]) or 0,
                        custo=parse_decimal(row[c["custo"]]) or 0,
                        lucro=parse_decimal(row[c["lucro"]]) or 0,
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

        # Relevância/Custo x Margem ficam em cache (achado 16/09/26, tela
        # levava 37s sem isso) -- limpa aqui pra não mostrar dado velho
        # depois de importar vendas novas.
        cache.clear()
