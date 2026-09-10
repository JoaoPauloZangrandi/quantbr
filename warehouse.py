"""Warehouse DuckDB do quantbr.

Convencao inegociavel do projeto (ver plano, camada L0):
  - toda tabela carrega _downloaded_at (o `as_of`) e _source_file
  - nada e sobrescrito em silencio: `replace_partition` troca uma particao inteira
    (ex.: um ano de COTAHIST) de forma atomica, e o historico do arquivo original
    continua em data/raw/
"""
from __future__ import annotations

import time
from contextlib import contextmanager

import duckdb
import pandas as pd

import config


@contextmanager
def connect(read_only: bool = False, *, tentativas: int = 6, espera: float = 5.0):
    """Abre conexao com o warehouse, esperando o lock se outro processo estiver escrevendo.

    DuckDB aceita um escritor por vez. Coletores rodando em paralelo (que e o caso normal
    aqui: COTAHIST demora minutos por ano enquanto NEFIN/BCB terminam em segundos) batem
    um no outro. Em vez de deixar o coletor morrer no meio, espera e tenta de novo -- a
    janela de escrita de cada coletor e curta, entao alguns segundos resolvem.
    """
    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            con = duckdb.connect(str(config.DB_PATH), read_only=read_only)
            break
        except duckdb.IOException as exc:
            if "lock" not in str(exc).lower():
                raise
            ultimo_erro = exc
            time.sleep(espera * (tentativa + 1))
    else:
        raise TimeoutError(
            f"warehouse travado por outro processo apos {tentativas} tentativas"
        ) from ultimo_erro
    try:
        yield con
    finally:
        con.close()


def table_exists(con, table: str) -> bool:
    rows = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchall()
    return bool(rows)


def replace_partition(con, table: str, df: pd.DataFrame, *, key: str, value) -> int:
    """Insere `df` em `table`, removendo antes as linhas onde key == value.

    Idempotente por construcao: reprocessar o mesmo ano/mes substitui, nao duplica.
    """
    con.register("_incoming", df)
    if not table_exists(con, table):
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM _incoming")
    else:
        con.execute(f"DELETE FROM {table} WHERE {key} = ?", [value])
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _incoming")
    con.unregister("_incoming")
    return len(df)


def summary(table: str) -> pd.DataFrame:
    with connect(read_only=True) as con:
        if not table_exists(con, table):
            return pd.DataFrame()
        return con.execute(f"SELECT * FROM {table} LIMIT 5").df()
