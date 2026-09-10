"""Banco Central: series do SGS via API publica JSON.

Uso no quantbr: taxa livre de risco alternativa (CDI/Selic), cambio para choque de BRL
nos testes de stress, e inflacao para retorno real. A taxa livre de risco PRIMARIA das
regressoes de fator continua sendo a do NEFIN, para nao misturar convencao com a
literatura brasileira -- o BCB entra como cross-check e para o que o NEFIN nao cobre.

Armadilha da API (verificada ao vivo, nao suposta): series de periodicidade DIARIA
aceitam janela de no maximo 10 anos por requisicao; acima disso a API devolve HTTP 406
com mensagem explicita. Series mensais nao tem esse limite. Por isso a paginacao abaixo.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

import warehouse
from ingest.base import get_json, now_utc

URL = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"
       "?formato=json&dataInicial={ini}&dataFinal={fim}")

INICIO = dt.date(2000, 1, 1)

# codigo -> (nome, diaria?)
SERIES = {
    11:   ("selic_diaria", True),      # % ao dia
    12:   ("cdi_diario", True),        # % ao dia
    432:  ("selic_meta", True),        # % a.a.
    1:    ("cambio_usd_ptax", True),   # R$/US$ venda
    433:  ("ipca_mensal", False),      # % no mes
    189:  ("igpm_mensal", False),
}


def _janelas(diaria: bool):
    """Gera (inicio, fim) respeitando o teto de 10 anos das series diarias."""
    hoje = dt.date.today()
    if not diaria:
        yield INICIO, hoje
        return
    ini = INICIO
    while ini < hoje:
        fim = min(dt.date(ini.year + 9, 12, 31), hoje)
        yield ini, fim
        ini = fim + dt.timedelta(days=1)


def _buscar(cod: int, diaria: bool) -> pd.DataFrame:
    partes = []
    for ini, fim in _janelas(diaria):
        url = URL.format(cod=cod, ini=ini.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
        dados = get_json(url, timeout=120)
        if dados:
            partes.append(pd.DataFrame(dados))
    if not partes:
        return pd.DataFrame(columns=["data", "valor"])
    return pd.concat(partes, ignore_index=True)


def carregar() -> int:
    frames = []
    for cod, (nome, diaria) in SERIES.items():
        try:
            df = _buscar(cod, diaria)
        except Exception as exc:  # uma serie fora do ar nao derruba a ingestao inteira
            print(f"  aviso: serie {cod} ({nome}) falhou: {type(exc).__name__}")
            continue
        if df.empty:
            print(f"  aviso: serie {cod} ({nome}) voltou vazia")
            continue
        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df = df.dropna(subset=["data"]).drop_duplicates(subset=["data"])
        df["serie"] = nome
        df["codigo_sgs"] = cod
        frames.append(df[["data", "serie", "codigo_sgs", "valor"]])
        print(f"  {nome:<18} {len(df):>7,} obs  ({df['data'].min():%Y-%m-%d} a {df['data'].max():%Y-%m-%d})")

    todo = pd.concat(frames, ignore_index=True)
    todo["_source_file"] = "api.bcb.gov.br/sgs"
    todo["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS bcb_sgs")
        con.register("_incoming", todo)
        con.execute("CREATE TABLE bcb_sgs AS SELECT * FROM _incoming")
        con.unregister("_incoming")
    return len(todo)


if __name__ == "__main__":
    print(f"total: {carregar():,} observacoes")
