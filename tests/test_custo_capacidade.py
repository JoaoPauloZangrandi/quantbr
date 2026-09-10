"""Trava a camada de custo e capacidade -- a que decide se um edge de capital pequeno e real.

POR QUE ESTA CAMADA EXISTE. A tese de operar onde instituicao nao entra so se sustenta se
o custo de negociar ali for pago. E o custo nao e detalhe: medido na base (2015+), o
spread mediano vai de 0,175% em papel acima de R$10 mi/dia para 3,279% abaixo de R$100
mil/dia. Dezenove vezes.

O numero que fecha o argumento, e ele tem duas metades:

    faixa de tamanho     custo ida-volta   capital que cabe (20 papeis, 5 pregoes)
    > R$ 10 bi                    0,20%    R$ 969 milhoes
    R$ 1-10 bi                    0,45%    R$  85 milhoes
    R$ 100 mi - 1 bi              1,39%    R$ 1,76 milhao
    < R$ 100 mi                   4,50%    R$ 0,11 milhao

A primeira metade e a oportunidade: nenhum fundo opera com R$1,76 milhao de capacidade.
A segunda e o pedagio: a 12 rebalanceamentos por ano, essa faixa custa 16,7% ao ano so de
custo, e a faixa abaixo custa 54%. Quase nenhuma anomalia publicada sobrevive a isso.

Conclusao que a base agora sustenta com numero: o espaco existe, mas exige GIRO BAIXO.
"""
from __future__ import annotations

import duckdb
import pytest

from emissor import EMOLUMENTO_B3, SQL_COM_BALANCO, TETO_PARTICIPACAO_ADTV


def test_tarifa_da_b3_e_a_de_swing_trade_pessoa_fisica():
    """0,0300% por lado: 0,0250% de liquidacao + 0,0050% de negociacao.

    Fonte: tabela de tarifas da B3, mercado a vista, consultada em 10/09/2026. Ja inclui
    PIS/COFINS e ISS. Corretagem NAO entra aqui -- varia por corretora e hoje e zero em
    boa parte delas, entao embutir um numero fixo enganaria.

    Se alguem trocar por uma tarifa de day trade (menor), o custo do backtest cai sem que
    a estrategia tenha melhorado.
    """
    assert EMOLUMENTO_B3 == pytest.approx(0.000300)
    assert 0 < EMOLUMENTO_B3 < 0.001, "tarifa fora de qualquer ordem de grandeza plausivel"


def test_custo_de_ida_e_volta_cobra_o_spread_inteiro_e_duas_tarifas():
    """Compra no ask, vende no bid: paga o spread INTEIRO, nao a metade.

    O erro comum e cobrar meio spread por perna e esquecer que sao duas pernas -- o que
    subestima o custo pela metade e faz estrategia de giro alto parecer viavel.
    """
    expr = "spread_mediano + 2 * {emolumento}".format(emolumento=EMOLUMENTO_B3)
    con = duckdb.connect(":memory:")
    # Spread de 1% -> ida e volta = 1% + 2 x 0,03% = 1,06%
    resultado = con.execute(
        f"SELECT CAST({expr} AS DOUBLE) FROM (SELECT 0.01::DOUBLE AS spread_mediano)"
    ).fetchone()[0]
    con.close()
    assert resultado == pytest.approx(0.0106)


def test_a_expressao_de_custo_do_modulo_e_a_testada_aqui():
    """Amarra o teste ao SQL de producao. Se a formula mudar la, quebra aqui."""
    sql = SQL_COM_BALANCO.format(emolumento=EMOLUMENTO_B3, teto=TETO_PARTICIPACAO_ADTV)
    assert f"spread_mediano + 2 * {EMOLUMENTO_B3}" in sql
    assert f"volume_mediano * {TETO_PARTICIPACAO_ADTV}" in sql


@pytest.mark.parametrize("capacidade_dia,papeis,pregoes,capital_esperado", [
    (17_600.0, 20, 5, 1_760_000.0),    # faixa R$100mi-1bi: R$1,76 milhao
    (1_100.0, 20, 5, 110_000.0),       # faixa <R$100mi: R$110 mil
    (9_696_000.0, 20, 5, 969_600_000.0),  # faixa >R$10bi: R$969 milhoes
])
def test_capital_que_cabe_em_cada_faixa(capacidade_dia, papeis, pregoes, capital_esperado):
    """A aritmetica da capacidade, com os numeros medidos na base.

    Existe para que a conclusao nao vire folclore: a faixa de R$100mi-1bi comporta
    R$1,76 milhao numa carteira de 20 papeis montada em 5 pregoes. Nenhum fundo opera
    com isso -- e e exatamente por isso que ela esta vazia de instituicao.
    """
    assert capacidade_dia * papeis * pregoes == pytest.approx(capital_esperado)


@pytest.mark.parametrize("custo_roundtrip,giros,custo_anual", [
    (0.0139, 12, 0.1668),   # R$100mi-1bi, mensal: 16,7% ao ano so de custo
    (0.0139, 4, 0.0556),    # trimestral: 5,6%
    (0.0139, 1, 0.0139),    # anual: 1,4%
    (0.0450, 12, 0.5400),   # <R$100mi, mensal: 54% ao ano -- inviavel
])
def test_o_giro_e_quem_decide_se_o_espaco_e_operavel(custo_roundtrip, giros, custo_anual):
    """O mesmo papel e viavel ou impossivel dependendo so da frequencia de rebalanceamento.

    E a razao de este teste existir: a conclusao "small cap tem edge" e incompleta sem
    dizer a que giro. A 12 giros por ano a faixa de R$100mi-1bi exige 16,7% de retorno
    bruto so para empatar.
    """
    assert custo_roundtrip * giros == pytest.approx(custo_anual, abs=1e-4)
