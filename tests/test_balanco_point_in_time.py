"""Trava o casamento do balanco com o mes: nada de olhar o futuro.

POR QUE ISTO E O TESTE MAIS IMPORTANTE DESTA CAMADA. Dado contabil e onde look-ahead
entra mais facil, porque o balanco descreve 31 de dezembro e so fica publico meses depois.
Usar o numero "do ano" sem perguntar quando ele saiu produz um book-to-market que o
investidor nao tinha como conhecer -- e o backtest fica maravilhoso por construcao.

O padrao da literatura e defasar 6 meses no atacado (Fama-French). A CVM permite fazer
melhor: `DT_RECEB` e a data em que o documento chegou. Medido em 2015: mediana de 88 dias
apos a referencia, p90 de 125, **maximo de 964**. A defasagem fixa erra justamente nas
empresas que atrasam balanco -- que sao as em dificuldade, e as que mais importam num
teste de valor.

O teste roda o MESMO SQL do modulo, extraido de `emissor.SQL_COM_BALANCO`. Teste que
reimplementa a regra nao prova nada sobre o pipeline.
"""
from __future__ import annotations

import duckdb
import pytest

from emissor import SQL_COM_BALANCO


def _sql_lateral() -> str:
    """A subconsulta de escolha do balanco, tirada do proprio modulo."""
    ini = SQL_COM_BALANCO.index("LEFT JOIN LATERAL (") + len("LEFT JOIN LATERAL (")
    fim = SQL_COM_BALANCO.index(") c ON TRUE")
    corpo = SQL_COM_BALANCO[ini:fim]
    # No modulo a subconsulta se refere a `b.cnpj` e `b.fim_do_mes`; aqui a tabela de
    # meses se chama `b` tambem, entao o texto entra sem adaptacao.
    return corpo.replace("dfp_wide d", "dfp_wide d")


# Caso real, da Petrobras: o balanco de 2014 so foi entregue em 24/04/2015 (versao 2), e o
# de 2015 em 21/03/2016. Entao janeiro e fevereiro de 2016 SO PODIAM conhecer o de 2014.
FILINGS = [
    # (cnpj, dt_refer, dt_receb, versao, patrimonio_liquido)
    ("PETR", "2014-12-31", "2015-04-24", 2, 310_700_000_000.0),
    ("PETR", "2015-12-31", "2016-03-21", 1, 257_900_000_000.0),
]


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE dfp_wide (cnpj VARCHAR, dt_refer DATE, dt_receb DATE,
                               versao INTEGER, patrimonio_liquido DOUBLE)
    """)
    con.executemany("INSERT INTO dfp_wide VALUES (?, ?::DATE, ?::DATE, ?, ?)", FILINGS)
    return con


def _balanco_em(con, fim_do_mes: str):
    con.execute(f"""
        CREATE OR REPLACE TABLE b AS
        SELECT 'PETR' AS cnpj, DATE '{fim_do_mes}' AS fim_do_mes
    """)
    return con.execute(f"""
        SELECT c.dt_refer, c.versao, c.patrimonio_liquido
        FROM b LEFT JOIN LATERAL ({_sql_lateral()}) c ON TRUE
    """).fetchone()


@pytest.mark.parametrize("fim_do_mes,refer_esperada", [
    ("2016-01-31", "2014-12-31"),   # o de 2015 ainda nao existia
    ("2016-02-29", "2014-12-31"),
    ("2016-03-31", "2015-12-31"),   # entregue em 21/03, ja e publico
    ("2016-07-31", "2015-12-31"),
])
def test_o_mes_so_enxerga_balanco_ja_entregue(fim_do_mes, refer_esperada):
    con = _con()
    linha = _balanco_em(con, fim_do_mes)
    con.close()
    assert linha is not None and linha[0] is not None, "deveria achar algum balanco"
    assert str(linha[0]) == refer_esperada, (
        f"em {fim_do_mes} o balanco usado deveria ser o de {refer_esperada}"
    )


def test_antes_da_primeira_entrega_nao_ha_balanco():
    """Empresa sem nada entregue fica com NULL, nao com o balanco futuro."""
    con = _con()
    linha = _balanco_em(con, "2015-01-31")
    con.close()
    assert linha[0] is None, "nenhum documento existia em jan/2015"


def test_entre_versoes_vale_a_que_ja_tinha_sido_entregue():
    """A mesma referencia e reapresentada; o backtest usa a versao que existia no dia.

    A v1 sai em fevereiro com um numero e a v3 refaz em junho com outro. Usar sempre a
    definitiva e look-ahead silencioso: quem operou em marco viu a v1.
    """
    con = _con()
    con.executemany("INSERT INTO dfp_wide VALUES (?, ?::DATE, ?::DATE, ?, ?)", [
        ("PETR", "2015-12-31", "2016-06-30", 3, 250_000_000_000.0),
    ])
    em_abril = _balanco_em(con, "2016-04-30")
    em_julho = _balanco_em(con, "2016-07-31")
    con.close()
    assert em_abril[1] == 1, "em abril so a versao 1 existia"
    assert em_julho[1] == 3, "em julho a versao 3 ja tinha sido entregue"
    assert em_abril[2] != em_julho[2], "as duas versoes trazem numeros diferentes"
