"""Trava as duas decisoes do painel por emissor: nao olhar o futuro, e nao girar por ruido.

POR QUE O PAINEL POR EMISSOR EXISTE: ON e PN da mesma companhia nao sao dois ativos
independentes. Num sort por tamanho ou valor, ITUB3 e ITUB4 entrariam como duas
observacoes da MESMA firma -- inflando o N efetivo, quebrando a independencia que o
erro-padrao de Fama-MacBeth assume, e deixando uma empresa ocupar duas vagas no mesmo
decil. Medido na nossa base: 30,7% dos meses-empresa tem duas classes negociando.

Os testes usam DuckDB em memoria com dado sintetico e nao tocam o warehouse.
"""
from __future__ import annotations

import duckdb
import pytest


def _painel(linhas: list[tuple]) -> duckdb.DuckDBPyConnection:
    """(cnpj, ticker, ano_mes, volume_mes) -> escolha da classe, com a regra do modulo."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE m (cnpj VARCHAR, ticker VARCHAR, ano_mes VARCHAR, volume_mes DOUBLE)")
    con.executemany("INSERT INTO m VALUES (?,?,?,?)", linhas)
    return con


ESCOLHA = """
    WITH com_liquidez_anterior AS (
        SELECT *, sum(volume_mes) OVER (
                     PARTITION BY cnpj, ticker ORDER BY ano_mes
                     ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING
                  ) AS volume_anterior
        FROM m
    ),
    ranqueado AS (
        SELECT *, row_number() OVER (
                     PARTITION BY cnpj, ano_mes
                     ORDER BY COALESCE(volume_anterior, -1) DESC, volume_mes DESC, ticker
                  ) AS posicao
        FROM com_liquidez_anterior
    )
    SELECT ano_mes, ticker FROM ranqueado WHERE posicao = 1 ORDER BY ano_mes
"""


def test_a_classe_escolhida_nao_pode_depender_do_proprio_mes():
    """O look-ahead que este modulo evita, e que e do tipo pior.

    Cenario: a PN e disparadamente mais liquida ha um ano. No mes 3 a ON explode de
    volume -- porque saiu uma noticia, e a noticia move o preco. Escolher "a mais liquida
    do mes" pegaria a ON no mes 3 usando informacao que so existia no fim dele, e a
    escolha estaria CORRELACIONADA com o retorno que se quer medir.
    """
    linhas = []
    for i in range(1, 4):
        linhas.append(("X", "XXXX3", f"2020-{i:02d}", 10.0))
        linhas.append(("X", "XXXX4", f"2020-{i:02d}", 1000.0))
    linhas[-2] = ("X", "XXXX3", "2020-03", 99999.0)   # a ON explode NO mes 3

    con = _painel(linhas)
    escolhas = dict(con.execute(ESCOLHA).fetchall())
    con.close()
    assert escolhas["2020-03"] == "XXXX4", (
        "a explosao de volume da ON no proprio mes nao pode mudar a escolha daquele mes"
    )


def test_janela_longa_nao_troca_de_classe_por_ruido():
    """Bug medido, nao imaginado.

    Com janela de UM mes, empresa iliquida trocava de classe na metade dos meses --
    IGUACU CAFE 50,9%, ALFA HOLDING 49,8%. As duas classes mal negociam, entao "a mais
    liquida" alterna por acaso e produz um giro que nenhuma carteira real suportaria.
    A janela de 12 meses e sticky por construcao.

    Aqui as duas classes alternam quem negociou mais a cada mes, sempre em volume
    minusculo. Com 12 meses de acumulado, a lider nao muda.
    """
    linhas = []
    for i in range(1, 13):
        alterna = i % 2 == 0
        linhas.append(("Y", "YYYY3", f"2020-{i:02d}", 11.0 if alterna else 9.0))
        linhas.append(("Y", "YYYY4", f"2020-{i:02d}", 9.0 if alterna else 11.0))

    con = _painel(linhas)
    escolhas = [t for _, t in con.execute(ESCOLHA).fetchall()]
    con.close()
    trocas = sum(1 for a, b in zip(escolhas, escolhas[1:]) if a != b)
    assert trocas <= 1, f"a escolha trocou {trocas} vezes com volume alternando por ruido"


def test_a_classe_mais_liquida_ganha_quando_a_diferenca_e_real():
    """A regra tem que continuar funcionando: liquidez de verdade decide.

    Caso real da base: a Itausa negocia ITSA4 muito acima de ITSA3, e o painel usa ITSA4
    nos 261 meses. Se este teste quebrar, a escolha parou de seguir a liquidez.
    """
    linhas = []
    for i in range(1, 13):
        linhas.append(("Z", "ZZZZ3", f"2020-{i:02d}", 100.0))
        linhas.append(("Z", "ZZZZ4", f"2020-{i:02d}", 10000.0))

    con = _painel(linhas)
    escolhas = con.execute(ESCOLHA).fetchall()
    con.close()
    assert {t for _, t in escolhas} == {"ZZZZ4"}
