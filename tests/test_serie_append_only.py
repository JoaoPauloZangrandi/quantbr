"""Trava a propriedade que torna backtest reproduzivel: o retorno de ontem nao muda.

O PROBLEMA REAL que motivou a etapa. A base ajustava preco por FATOR ACUMULADO
RETROATIVO: quando um desdobramento acontece hoje, todo o preco ajustado do passado e
dividido de novo. O numero de 2010 que voce leu em marco nao e o mesmo que voce le em
setembro. Um backtest rodado duas vezes da resultado diferente e nao ha como saber se a
diferenca veio do codigo ou do dado -- que e exatamente o tipo de coisa que faz uma casa
de research perder a confianca no proprio resultado.

O desenho do CRSP, a base que a literatura usa, e o inverso: o RETORNO e a primitiva.

    R(t) = [ P(t) x F(t) + D(t) ] / P(t-1) - 1

depende so de t e t-1. Nenhum evento posterior entra na conta.

Este teste roda `painel.SQL_RETORNOS` -- a MESMA expressao que o painel usa -- sobre um
banco DuckDB em memoria com dado sintetico. Nao toca no warehouse. Se alguem trocar a
formula do painel por uma que olhe para a frente, este teste quebra.
"""
from __future__ import annotations

import duckdb
import pytest

from painel import SQL_RETORNOS

# Serie sintetica: 6 pregoes de um papel a R$10, sem evento nenhum ate o dia 4.
# No dia 4 ha um desdobramento 2:1 -- o preco cai para 5 e o fator retroativo passa a
# valer 2 para todos os dias ANTERIORES.
BASE = [
    # (data, fechamento, fator_acum sem o evento do dia 5, com o evento do dia 5)
    ("2026-01-02", 10.0),
    ("2026-01-05", 11.0),
    ("2026-01-06", 12.0),
    ("2026-01-07", 6.0),    # dia ex do desdobramento 2:1
    ("2026-01-08", 6.5),
    ("2026-01-09", 7.0),
]


def _monta(con, fatores_por_data: dict[str, float]) -> None:
    """Monta acoes_diario sintetica com o produto retroativo dos fatores dados.

    Reproduz a convencao do painel: `fator_acum` de um dia e o produto dos fatores de
    todo evento POSTERIOR a ele, e o preco ajustado e fechamento / fator_acum.
    """
    linhas = []
    for i, (data, fech) in enumerate(BASE):
        posteriores = [f for d, f in fatores_por_data.items()
                       if d > data]
        acum = 1.0
        for f in posteriores:
            acum *= f
        linhas.append((f"TESTE3", data, fech, acum))
    con.execute("""
        CREATE OR REPLACE TABLE acoes_diario (
            ticker VARCHAR, data DATE, fechamento DOUBLE, fator_acum DOUBLE
        )
    """)
    con.executemany("INSERT INTO acoes_diario VALUES (?, ?::DATE, ?, ?)", linhas)
    con.execute("""
        CREATE OR REPLACE TABLE acoes_diario AS
        SELECT *, fechamento / fator_acum AS fechamento_ajustado,
                  fechamento / fator_acum AS fechamento_retorno_total
        FROM acoes_diario
    """)


def _retornos(fatores_por_data: dict[str, float]) -> dict[str, float]:
    con = duckdb.connect(":memory:")
    _monta(con, fatores_por_data)
    df = con.execute(f"""
        SELECT data::VARCHAR AS data, {SQL_RETORNOS} FROM acoes_diario ORDER BY data
    """).df()
    con.close()
    return {r["data"]: r["retorno_qtd"] for _, r in df.iterrows()}


def test_evento_novo_nao_altera_retorno_anterior():
    """O teste central da Etapa 6.

    Cenario: a serie ja tem um desdobramento 2:1 em 07/01. Depois aparece um segundo
    evento, 3:1 em 09/01. O fator acumulado de TODOS os dias anteriores muda -- e o
    preco ajustado deles muda junto. O retorno, nao.
    """
    so_um = {"2026-01-07": 2.0}
    dois = {"2026-01-07": 2.0, "2026-01-09": 3.0}

    r1, r2 = _retornos(so_um), _retornos(dois)
    anteriores = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    for data in anteriores:
        assert r1[data] == pytest.approx(r2[data], rel=1e-12), (
            f"o retorno de {data} mudou por causa de um evento posterior -- "
            "a serie deixou de ser append-only"
        )


def test_o_preco_ajustado_MUDA_com_evento_novo():
    """A contraparte, e o motivo de o retorno ser a primitiva e nao o preco.

    Este teste documenta o comportamento que NAO da para evitar: o nivel do preco
    ajustado e relativo ao fim da serie, entao ele se remede a cada evento novo. Por isso
    preco ajustado serve para desenhar grafico, e retorno serve para calcular.
    """
    con = duckdb.connect(":memory:")
    _monta(con, {"2026-01-07": 2.0})
    antes = con.execute("SELECT fechamento_ajustado FROM acoes_diario ORDER BY data").fetchall()
    _monta(con, {"2026-01-07": 2.0, "2026-01-09": 3.0})
    depois = con.execute("SELECT fechamento_ajustado FROM acoes_diario ORDER BY data").fetchall()
    con.close()
    assert antes != depois, (
        "se o preco ajustado NAO mudou, o fator retroativo parou de ser aplicado -- "
        "provavelmente o ajuste quebrou"
    )


def test_desdobramento_nao_vira_retorno_de_menos_50_por_cento():
    """A razao de existir do ajuste, em uma linha.

    No dia ex do 2:1 o preco cai de 12,00 para 6,00. Sem ajuste isso e -50% de retorno,
    o que e simplesmente falso: quem tinha a acao ficou com duas, e nao perdeu nada.
    """
    r = _retornos({"2026-01-07": 2.0})
    assert r["2026-01-07"] == pytest.approx(0.0, abs=1e-12)
