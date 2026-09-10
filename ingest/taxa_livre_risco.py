"""Taxa livre de risco brasileira (CDI e Selic), via API do Banco Central.

POR QUE ISTO VOLTOU DEPOIS DE TER SIDO EXCLUIDO

Na limpeza de 02/09/2026 todo dado que nao fosse acao da B3 foi apagado, o `bcb_sgs`
incluido. Mas testar paper de asset pricing sem taxa livre de risco nao da: retorno
excedente, indice de Sharpe, alfa, premio de risco -- tudo comeca subtraindo a taxa livre
de risco do retorno do ativo. E uma serie so, ~6.700 linhas, e sem ela metade das contas
da literatura simplesmente nao fecha.

Ficou numa tabela separada de proposito. O painel de acoes continua sendo so acoes.

CONVENCAO

O SGS entrega CDI e Selic em **percentual ao dia** (0,0546 significa 0,0546% no dia, nao
5,46%). A coluna `fator_dia` ja traz a conversao para fator multiplicativo:

    fator_dia = 1 + valor/100

Acumular retorno livre de risco entre duas datas e o produto de `fator_dia` no intervalo.

ARMADILHA DA API, ja verificada ao vivo e tratada em `ingest.base.get_json`: o servidor do
BCB as vezes devolve **HTTP 200 com corpo HTML** de erro em vez de JSON, de forma
intermitente. Sem checar o corpo, a serie sumia em silencio. E o SGS limita serie diaria a
10 anos por requisicao (HTTP 406), dai a paginacao.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

import warehouse
from ingest.base import get_json, now_utc

URL = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"
       "?formato=json&dataInicial={ini}&dataFinal={fim}")

INICIO = dt.date(2005, 1, 1)   # mesmo inicio do painel de acoes

SERIES = {
    12:  "cdi",          # % ao dia -- a referencia usada no mercado brasileiro
    11:  "selic",        # % ao dia
}


def _janelas():
    """O SGS aceita no maximo 10 anos por requisicao em serie diaria."""
    hoje = dt.date.today()
    ini = INICIO
    while ini < hoje:
        fim = min(dt.date(ini.year + 9, 12, 31), hoje)
        yield ini, fim
        ini = fim + dt.timedelta(days=1)


def carregar() -> int:
    frames = []
    for cod, nome in SERIES.items():
        partes = []
        for ini, fim in _janelas():
            dados = get_json(URL.format(cod=cod, ini=ini.strftime("%d/%m/%Y"),
                                        fim=fim.strftime("%d/%m/%Y")), timeout=120)
            if dados:
                partes.append(pd.DataFrame(dados))
        if not partes:
            print(f"  aviso: serie {nome} voltou vazia")
            continue
        df = pd.concat(partes, ignore_index=True)
        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
        df["valor_pct_dia"] = pd.to_numeric(df["valor"], errors="coerce")
        df = df.dropna(subset=["data"]).drop_duplicates(subset=["data"])
        df["fator_dia"] = 1 + df["valor_pct_dia"] / 100.0
        df["serie"] = nome
        frames.append(df[["data", "serie", "valor_pct_dia", "fator_dia"]])
        print(f"  {nome:<8} {len(df):>7,} obs  "
              f"({df['data'].min():%Y-%m-%d} a {df['data'].max():%Y-%m-%d})")

    todo = pd.concat(frames, ignore_index=True)
    todo["_source_file"] = "api.bcb.gov.br/sgs"
    todo["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS taxa_livre_risco")
        con.register("_tlr", todo)
        con.execute("CREATE TABLE taxa_livre_risco AS SELECT * FROM _tlr")
        con.unregister("_tlr")
    return len(todo)


if __name__ == "__main__":
    print(f"{carregar():,} observacoes de taxa livre de risco")
