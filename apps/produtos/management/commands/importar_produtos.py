import re
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


def _normalizar_descricao(valor) -> str:
    return " ".join(str(valor or "").strip().upper().split())


def _palavras(texto: str) -> set[str]:
    """Palavras de 4+ letras (ignora MG/ML/CPR/C/30 etc.) -- usado só pra
    detectar se duas descrições são do mesmo produto ou não têm nada a
    ver (ver comentário do BUG de código reaproveitado abaixo)."""
    return set(w for w in re.split(r"[^A-ZÀ-Ü0-9]+", (texto or "").upper()) if len(w) >= 4)


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

        # BUG REAL encontrado 15/09/26: o "Código" da árvore mercadológica
        # e a "Etiqueta" do cadastro de estoque não são o mesmo valor pro
        # MESMO produto físico em boa parte dos casos (ex. MOUNJARO 5MG:
        # árvore usa '124037', estoque usa '104644') -- o join por
        # etiqueta/EAN falhava silenciosamente e o produto virava "sem
        # classificação" mesmo a árvore tendo a classificação certa numa
        # OUTRA linha. Medido: 26.936 produtos "sem classificação"
        # (R$ 16M em vendas, 36% do total -- a MAIOR "classificação" da
        # tela de Relevância era essa) tinham 100% um "gêmeo" com a MESMA
        # DESCRIÇÃO já classificado pela árvore. Corrigido: guarda a
        # classificação por descrição normalizada durante o loop da
        # árvore, usa como fallback pro cadastro de estoque que não bateu
        # por código. Só 30 descrições (0,07%) têm classificação ambígua
        # (2+ classificações diferentes pra mesma descrição, ex. remédio
        # RX vs USO CONTÍNUO) -- essas ficam de fora do fallback (mantidas
        # sem classificação, não dá pra adivinhar qual delas é a certa).
        classificacoes_vistas: dict[str, set[str]] = {}
        linhas_arvore = list(df_arvore.iterrows())
        for _, row in linhas_arvore:
            cc = str(row.get("Classificação") or "").strip()
            if cc:
                desc_norm = _normalizar_descricao(row.get("Descrição"))
                if desc_norm:
                    classificacoes_vistas.setdefault(desc_norm, set()).add(cc)
        classificacao_por_descricao = {
            desc: next(iter(ccs)) for desc, ccs in classificacoes_vistas.items() if len(ccs) == 1
        }

        codigo_reaproveitado = 0
        for _, row in linhas_arvore:
            chaves = chaves_possiveis(row.get("Código"))
            if not chaves:
                continue
            etiqueta_str = _normalizar_codigo(row.get("Código"))

            estoque_row = next((estoque_por_etiqueta[c] for c in chaves if c in estoque_por_etiqueta), None)
            ean, preco_venda, preco_ref = "", None, None
            fabricante = str(row.get("Fabricante") or "").strip()
            descricao_arvore = str(row.get("Descrição") or "").strip()
            descricao = descricao_arvore
            classificacao_completa = str(row.get("Classificação") or "").strip()

            if estoque_row is not None:
                ean = _normalizar_codigo(estoque_row.get("Código de Barras"))
                preco_venda = parse_decimal(estoque_row.get("Preço Venda"))
                preco_ref = parse_decimal(estoque_row.get("Preço Referencial"))
                fabricante = fabricante or str(estoque_row.get("Fabricante") or "").strip()
                descricao_estoque = str(estoque_row.get("Produto") or "").strip()
                vistos.update(chaves_possiveis(estoque_row.get("Etiqueta")))

                # BUG REAL encontrado 15/09/26 (Gabriel filtrou "GENÉRICOS"
                # e vieram itens de outras classificações): o "Código" da
                # árvore é um identificador INTERNO do ERP que às vezes é
                # REAPROVEITADO com o tempo pra um produto diferente (ex.
                # código 78881: a árvore diz "SAB LIQ REXONA...", o estoque
                # (mais atual, é de onde vem o EAN de verdade) diz "ABS
                # ALWAYS..." -- são produtos completamente diferentes,
                # zero palavra em comum). Nesse caso a Descrição/
                # Classificação da árvore NÃO são confiáveis pra esse EAN
                # -- usa o texto do estoque (mais atual) e tenta recuperar
                # a classificação certa pela descrição (mesmo mecanismo já
                # usado no 2º loop pra código sem match nenhum); se não
                # achar, fica sem classificação mesmo -- errado é pior que
                # "sem".
                if descricao_estoque and descricao_arvore and not (_palavras(descricao_estoque) & _palavras(descricao_arvore)):
                    codigo_reaproveitado += 1
                    descricao = descricao_estoque
                    classificacao_completa = classificacao_por_descricao.get(_normalizar_descricao(descricao_estoque), "")
                else:
                    descricao = descricao_arvore or descricao_estoque

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

        # Produtos do cadastro de estoque que a árvore não classificou por
        # CÓDIGO -- tenta recuperar a classificação pela descrição (ver
        # comentário acima) antes de aceitar "sem classificação" de vez.
        sem_classificacao, recuperados_por_descricao = 0, 0
        for _, row in df_estoque.iterrows():
            chaves = chaves_possiveis(row.get("Etiqueta"))
            if chaves & vistos:
                continue
            ean = _normalizar_codigo(row.get("Código de Barras"))
            if not ean or ean.lower() == "nan":
                continue
            etiqueta = _normalizar_codigo(row.get("Etiqueta"))
            descricao = str(row.get("Produto") or "").strip()
            classificacao_completa = classificacao_por_descricao.get(_normalizar_descricao(descricao), "")

            defaults = {
                "etiqueta": etiqueta,
                "descricao": descricao,
                "fabricante": str(row.get("Fabricante") or "").strip(),
                "preco_venda_atual": parse_decimal(row.get("Preço Venda")),
                "preco_referencial": parse_decimal(row.get("Preço Referencial")),
            }
            if classificacao_completa:
                defaults["classificacao_completa"] = classificacao_completa
                defaults["classificacao"] = extrair_classificacao_nivel1(classificacao_completa)
                defaults["subclassificacao"] = extrair_subclassificacao_nivel2(classificacao_completa)

            _, created = Produto.objects.update_or_create(ean=ean, defaults=defaults)
            criados += created
            atualizados += not created
            if classificacao_completa:
                recuperados_por_descricao += 1
            else:
                sem_classificacao += 1

        self.stdout.write(self.style.SUCCESS(f"{criados} produto(s) criado(s), {atualizados} atualizado(s)."))
        if codigo_reaproveitado:
            self.stdout.write(self.style.WARNING(
                f"{codigo_reaproveitado} produto(s) com código interno reaproveitado (árvore e estoque "
                f"descrevem produtos diferentes pro mesmo código) -- descrição/classificação vieram do "
                f"estoque (mais atual), recuperando a classificação certa pela descrição quando possível."
            ))
        if recuperados_por_descricao:
            self.stdout.write(self.style.SUCCESS(
                f"{recuperados_por_descricao} produto(s) recuperaram classificação via descrição "
                f"(código não batia entre os 2 cadastros, mas a descrição sim)."
            ))
        if sem_classificacao:
            self.stdout.write(self.style.WARNING(
                f"{sem_classificacao} produto(s) do cadastro de estoque sem classificação de "
                f"verdade (não bateram nem por código nem por descrição)."
            ))
