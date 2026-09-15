# -*- coding: utf-8 -*-
"""
Backup dos bancos SQLite de verdade (dado, não código -- por isso nunca
entram no Git, ver README -> Pendências -> Backup/infraestrutura).

Por que isso existe: o `db.sqlite3` do monitor-precos e o
`_precos_continuos.sqlite3` do robo_cotacao ficam sendo reescritos o
tempo todo (toda importação, toda sincronização, o robô a cada 30min) --
um arquivo que nunca "para quieto" é exatamente o tipo de coisa que o
OneDrive tem dificuldade de sincronizar até o fim (sempre fica "atrás",
ícone de sincronizando em vez de confirmado). Achado ao vivo em
16/09/26: o ícone do Explorer mostrava "sincronizando" pro db.sqlite3
mesmo bem depois da última alteração.

O que esse script faz: tira uma cópia ESTÁTICA (que não muda mais depois
de criada) de cada banco, usando o método de backup de verdade do
SQLite (`sqlite3 .backup`, não um `copy` de arquivo cru -- copiar um
banco em uso com copy pode pegar ele no meio de uma escrita e corromper
a cópia; o backup API do SQLite é seguro mesmo com o banco sendo usado
ao mesmo tempo). Como a cópia parada nunca mais é tocada, o OneDrive
consegue sincronizar ela até o fim -- o "ao vivo" pode continuar
sincronizando devagar, mas sempre vai ter uma foto recente e completa
garantida na nuvem.

Uso manual:
    python backup_bancos.py

Mantém só os 10 backups mais recentes de cada banco (apaga os mais
velhos) -- pra não crescer sem limite (cada cópia do monitor-precos
fica na casa de 150-200MB).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MANTER_ULTIMOS = 10

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_BACKUPS = PASTA_PROJETO.parent.parent / "BACKUPS DB"

BANCOS = {
    "monitor_precos": PASTA_PROJETO / "db.sqlite3",
    "robo_cotacao_precos": PASTA_PROJETO.parent.parent / "robo_cotacao" / "_precos_continuos.sqlite3",
}


def _backup_um(nome: str, origem: Path) -> Path | None:
    if not origem.exists():
        print(f"[{nome}] não encontrei '{origem}' -- pulando.")
        return None

    PASTA_BACKUPS.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    destino = PASTA_BACKUPS / f"{nome}_{carimbo}.sqlite3"

    origem_con = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    destino_con = sqlite3.connect(destino)
    try:
        origem_con.backup(destino_con)
    finally:
        destino_con.close()
        origem_con.close()

    tamanho_mb = destino.stat().st_size / (1024 * 1024)
    print(f"[{nome}] backup criado: {destino.name} ({tamanho_mb:.1f} MB)")
    return destino


def _limpar_antigos(nome: str):
    existentes = sorted(PASTA_BACKUPS.glob(f"{nome}_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for antigo in existentes[MANTER_ULTIMOS:]:
        antigo.unlink()
        print(f"[{nome}] removido backup antigo: {antigo.name}")


def main():
    print(f"Pasta de backup: {PASTA_BACKUPS}\n")
    algum_erro = False
    for nome, origem in BANCOS.items():
        try:
            if _backup_um(nome, origem):
                _limpar_antigos(nome)
        except Exception as exc:
            algum_erro = True
            print(f"[{nome}] ERRO ao fazer backup: {exc}")
        print()
    return 1 if algum_erro else 0


if __name__ == "__main__":
    sys.exit(main())
