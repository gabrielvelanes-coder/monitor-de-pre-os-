"""Geocodifica o endereço dos concorrentes captados via Nominatim/
OpenStreetMap (gratuito, sem chave de API) -- pra dar distância REAL
loja-nossa x concorrente no Monitor de Preço, não só a distância até o
centro da cidade que o robô já captura.

Reimplementação da MESMA lógica/correções já validadas em
`robo_cotacao/mapa_concorrentes.py` (projetos não compartilham código-fonte,
só dados/regras -- ver README) -- inclui os 2 bugs reais já corrigidos lá:
1. Não gruda a cidade padrão na query se o endereço já tem uma cidade
   embutida (comum em endereço de concorrente vindo do Preço da Hora) --
   colar sempre gerava "...SALVADOR, Itabuna" (2 cidades contraditórias) e
   quebrava a geocodificação de qualquer coisa fora da cidade padrão.
2. Só cacheia SUCESSO -- falha (rate-limit temporário, blip de rede) nunca
   fica salva pra sempre, senão um endereço que teria funcionado numa nova
   tentativa fica "sem resultado" permanentemente.

Respeita o limite de 1 requisição/segundo da Nominatim Usage Policy --
demora minutos com centenas de endereços únicos. Rodar como comando manual
(não faz sentido no meio de uma request web)."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.captacao.models import PrecoCaptado

_USER_AGENT = "monitor-precos-velanes/1.0 (uso interno)"
_CAMINHO_CACHE = os.path.join(settings.DADOS_ENTRADA, "_geocode_cache_concorrentes.json")


def _carregar_cache() -> dict:
    if os.path.exists(_CAMINHO_CACHE):
        try:
            with open(_CAMINHO_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _salvar_cache(cache: dict):
    with open(_CAMINHO_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _consultar_nominatim(query: str) -> tuple[float, float] | None:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "br"})
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read())
            if dados:
                return float(dados[0]["lat"]), float(dados[0]["lon"])
    except Exception:
        pass
    return None


def _geocodificar_um(endereco: str, cidade_busca: str) -> tuple[float, float] | None:
    resultado = _consultar_nominatim(endereco)
    if resultado:
        return resultado
    cidade_padrao = f"{cidade_busca}, BA, Brasil" if cidade_busca else ""
    if cidade_padrao and cidade_busca.lower() not in endereco.lower():
        time.sleep(1.0)
        return _consultar_nominatim(f"{endereco}, {cidade_padrao}")
    return None


class Command(BaseCommand):
    help = "Geocodifica (lat/lon) o endereço dos PrecoCaptado de concorrente ainda sem coordenada."

    def handle(self, *args, **options):
        pendentes = list(
            PrecoCaptado.objects.filter(rede__tipo="concorrente", lat__isnull=True)
            .values("endereco", "cidade_busca").distinct()
        )
        if not pendentes:
            self.stdout.write(self.style.SUCCESS("Nenhum endereço de concorrente pendente de geocodificação."))
            return

        cache = _carregar_cache()
        resolvidos, falhas = 0, 0
        for i, item in enumerate(pendentes, start=1):
            endereco, cidade = item["endereco"], item["cidade_busca"]
            if endereco in cache:
                coords = tuple(cache[endereco])
            else:
                coords = _geocodificar_um(endereco, cidade)
                if coords:
                    cache[endereco] = list(coords)
                time.sleep(1.0)  # respeita 1 req/s da Nominatim mesmo em cache miss

            if coords:
                PrecoCaptado.objects.filter(endereco=endereco, rede__tipo="concorrente").update(
                    lat=coords[0], lon=coords[1]
                )
                resolvidos += 1
            else:
                falhas += 1

            if i % 20 == 0 or i == len(pendentes):
                self.stdout.write(f"  {i}/{len(pendentes)} endereços processados...")

        _salvar_cache(cache)
        self.stdout.write(self.style.SUCCESS(
            f"{resolvidos} endereço(s) geocodificado(s), {falhas} sem resultado (Nominatim não achou)."
        ))
