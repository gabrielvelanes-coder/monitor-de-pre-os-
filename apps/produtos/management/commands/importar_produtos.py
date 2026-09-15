from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.produtos.models import Produto
from apps.produtos.utils import (
    chaves_possiveis, extrair_classificacao_nivel1, extrair_subclassificacao_nivel2, parse_decimal,
)

ARQUIVO_ARVORE_PADRAO = "_cadastro_arvore_mercadologica.xlsx"
ARQUIVO_ESTOQUE_PADRAO = "_cadastro_base_estoque.xlsx"


def _normalizar_codigo(valor) -> str:
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") else texto


class Command(BaseCommand):
    help = (
        "Cruza o cadastro base de estoque (EAN, preço de venda, fabricante) com a "
        "árvore mercadológica (classificação, curva ABC) via etiqueta/código interno "
        "-- os dois relatórios do ERP não compartilham EAN diretamente. Gera o "
        "cadastro de Produto usado pra relevância (Classificação) e pro Monitor de Preço."
    )

    def add_arguments(self, parser):
        parser.add_argument("--arvore", default=None)
        parser.add_argument("--estoque", default=None)

    @transaction.atomic
    def handle(self, *args, **options):
        caminho_arvore = Path(options["arvore"]) if options["arvore"] else settings.DADOS_ENTRADA / ARQUIVO_ARVORE_PADRAO
        caminho_estoque = Path(options["estoque"]) if options["estoque"] else settings.DADOS_ENTRADA / ARQUIVO_ESTOQUE_PADRAO
        if not caminho_arvore.exists():
            raise CommandError(f"Não encontrei '{caminho_arvore}'.")
        if not caminho_estoque.exists():
            raise CommandError(f"Não encontrei '{caminho_estoque}'.")

        df_arvore = pd.read_excel(caminho_arvore)
        df_estoque = pd.read_excel(caminho_estoque)

        # Índice do cadastro de estoque por TODAS as chaves possíveis da
        # etiqueta -- é por aqui que cruzamos com a árvore (não tem EAN em comum).
        estoque_por_etiqueta = {}
        for _, row in df_estoque.iterrows():
            for chave in chaves_possiveis(row.get("Etiqueta")):
                estoque_por_etiqueta.setdefault(chave, row)

        criados, atualizados = 0, 0
        vistos: set[str] = set()  # chaves de etiqueta já cobertas pelo loop da árvore

        for _, row in df_arvore.iterrows():
            chaves = chaves_possiveis(row.get("Código"))
            if not chaves:
                continue
            etiqueta_str = _normalizar_codigo(row.get("Código"))

            estoque_row = next((estoque_por_etiqueta[c] for c in chaves if c in estoque_por_etiqueta), None)
            ean, preco_venda, preco_ref = "", None, None
            fabricante = str(row.get("Fabricante") or "").strip()
            descricao = str(row.get("Descrição") or "").strip()
            if estoque_row is not None:
                ean = _normalizar_codigo(estoque_row.get("Código de Barras"))
                preco_venda = parse_decimal(estoque_row.get("Preço Venda"))
                preco_ref = parse_decimal(estoque_row.get("Preço Referencial"))
                fabricante = fabricante or str(estoque_row.get("Fabricante") or "").strip()
                descricao = descricao or str(estoque_row.get("Produto") or "").strip()
                vistos.update(chaves_possiveis(estoque_row.get("Etiqueta")))

            classificacao_completa = str(row.get("Classificação") or "").strip()
            _, created = Produto.objects.update_or_create(
                etiqueta=etiqueta_str,
                defaults={
                    "ean": ean,
                    "descricao": descricao,
                    "fabricante": fabricante,
                    "classificacao_completa": classificacao_completa,
                    "classificacao": extrair_classificacao_nivel1(classificacao_completa),
                    "subclassificacao": extrair_subclassificacao_nivel2(classificacao_completa),
                    "curva_valor": str(row.get("Curva Valor") or "").strip(),
                    "curva_qtd": str(row.get("Curva Qtd.") or "").strip(),
                    "preco_venda_atual": preco_venda,
                    "preco_referencial": preco_ref,
                },
            )
            criados += created
            atualizados += not created

        # Produtos do cadastro de estoque que a árvore não classificou --
        # importa mesmo assim (sem classificação), pra não sumir do
        # Monitor de Preço por falta de categoria.
        sem_classificacao = 0
        for _, row in df_estoque.iterrows():
            chaves = chaves_possiveis(row.get("Etiqueta"))
            if chaves & vistos:
                continue
            ean = _normalizar_codigo(row.get("Código de Barras"))
            if not ean or ean.lower() == "nan":
                continue
            etiqueta = _normalizar_codigo(row.get("Etiqueta"))
            _, created = Produto.objects.update_or_create(
                ean=ean,
                defaults={
                    "etiqueta": etiqueta,
                    "descricao": str(row.get("Produto") or "").strip(),
                    "fabricante": str(row.get("Fabricante") or "").strip(),
                    "preco_venda_atual": parse_decimal(row.get("Preço Venda")),
                    "preco_referencial": parse_decimal(row.get("Preço Referencial")),
                },
            )
            criados += created
            atualizados += not created
            sem_classificacao += created

        self.stdout.write(self.style.SUCCESS(f"{criados} produto(s) criado(s), {atualizados} atualizado(s)."))
        if sem_classificacao:
            self.stdout.write(self.style.WARNING(
                f"{sem_classificacao} produto(s) do cadastro de estoque sem classificação "
                f"(não bateram com nenhuma linha da árvore mercadológica)."
            ))
