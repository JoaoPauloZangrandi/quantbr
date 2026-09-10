"""COTAHIST da B3: a espinha dorsal de precos, livre de survivorship bias.

Por que esta e a fonte primaria e nao o yfinance/brapi:
    o arquivo anual COTAHIST contem TODO ticker que negociou naquele ano. Empresa que
    quebrou, foi comprada ou saiu da bolsa continua la, no ano em que ainda existia.
    Universo montado a partir de ticker que existe hoje apaga justamente os fracassos,
    e a literatura estima 5-15% a.a. de inflacao de retorno por causa disso.

Precos vem CRUS (sem ajuste por provento). O ajuste e responsabilidade do modulo
master/, que constroi o fator a partir dos proventos da B3. Aqui nunca se ajusta nada.

Layout do registro tipo 01 (245 caracteres), conforme o manual da B3.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

import config
import warehouse
from ingest.base import download, now_utc

BASE_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
RAW_DIR = config.RAW / "b3_cotahist"

# (nome, inicio_1based, tamanho, tipo)
#   'v99' = inteiro com 2 casas decimais implicitas (dividir por 100)
LAYOUT = [
    ("tipreg",  1,   2, "str"),
    ("data",    3,   8, "str"),
    ("codbdi",  11,  2, "str"),   # 02 = lote padrao
    ("ticker",  13, 12, "str"),
    ("tpmerc",  25,  3, "str"),   # 010 = mercado a vista
    ("nome_res", 28, 12, "str"),
    ("especi",  40, 10, "str"),   # ON, PN, UNT, CI...
    ("prazot",  50,  3, "str"),
    ("modref",  53,  4, "str"),   # moeda de referencia (R$)
    ("abertura", 57, 13, "v99"),
    ("maxima",  70, 13, "v99"),
    ("minima",  83, 13, "v99"),
    ("media",   96, 13, "v99"),
    ("fechamento", 109, 13, "v99"),
    ("melhor_compra", 122, 13, "v99"),
    ("melhor_venda", 135, 13, "v99"),
    ("negocios", 148, 5, "int"),
    ("quantidade", 153, 18, "int"),
    ("volume",  171, 18, "v99"),
    ("preco_exercicio", 189, 13, "v99"),
    ("indopc",  202,  1, "str"),
    ("data_venc", 203, 8, "str"),
    ("fator_cotacao", 211, 7, "int"),  # 1 ou 1000 (papel cotado por lote de mil)
    ("pontos_exercicio", 218, 13, "v99"),
    ("isin",    231, 12, "str"),   # chave de identidade do papel -> usada no master/
    ("dismes",  243,  3, "str"),
]

COLSPECS = [(ini - 1, ini - 1 + tam) for _, ini, tam, _ in LAYOUT]
NAMES = [n for n, _, _, _ in LAYOUT]


def raw_path(ano: int) -> Path:
    return RAW_DIR / f"COTAHIST_A{ano}.ZIP"


def baixar(ano: int, *, force: bool = False) -> Path:
    """Baixa o arquivo anual. O ano corrente muda todo dia, entao force=True nele."""
    return download(BASE_URL.format(ano=ano), raw_path(ano), force=force)


def parse(path: Path, *, apenas_vista: bool = True) -> pd.DataFrame:
    """Le o ZIP e devolve DataFrame tipado.

    apenas_vista=True mantem so TPMERC 010 (mercado a vista), descartando opcoes e
    termo -- que sao a maior parte das linhas do arquivo.
    """
    with zipfile.ZipFile(path) as zf:
        nome = [n for n in zf.namelist() if n.upper().endswith(".TXT")][0]
        bruto = zf.read(nome)

    # Primeira e ultima linha sao header (00) e trailer (99): read_fwf as le e o filtro
    # de tipreg == '01' as descarta.
    df = pd.read_fwf(
        io.BytesIO(bruto),
        colspecs=COLSPECS,
        names=NAMES,
        dtype=str,
        encoding="latin-1",
        header=None,
    )
    df = df[df["tipreg"] == "01"].copy()
    if apenas_vista:
        df = df[df["tpmerc"] == "010"].copy()

    for nome_col, _, _, tipo in LAYOUT:
        if tipo == "v99":
            df[nome_col] = pd.to_numeric(df[nome_col], errors="coerce") / 100.0
        elif tipo == "int":
            df[nome_col] = pd.to_numeric(df[nome_col], errors="coerce").astype("Int64")
        else:
            df[nome_col] = df[nome_col].astype("string").str.strip()

    df["data"] = pd.to_datetime(df["data"], format="%Y%m%d", errors="coerce")
    df = df.drop(columns=["tipreg", "prazot", "indopc", "dismes", "data_venc",
                          "preco_exercicio", "pontos_exercicio"])
    return df.reset_index(drop=True)


def carregar(ano: int, *, force_download: bool = False) -> int:
    """Baixa, parseia e grava o ano no warehouse. Idempotente (substitui o ano inteiro)."""
    path = baixar(ano, force=force_download)
    df = parse(path)
    df["ano"] = ano
    df["_source_file"] = path.name
    df["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        n = warehouse.replace_partition(con, "b3_cotahist", df, key="ano", value=ano)
    return n


if __name__ == "__main__":
    import sys

    anos = [int(a) for a in sys.argv[1:]] or [pd.Timestamp.today().year]
    for ano in anos:
        atual = ano == pd.Timestamp.today().year
        n = carregar(ano, force_download=atual)
        print(f"{ano}: {n:>9,} linhas de mercado a vista")
