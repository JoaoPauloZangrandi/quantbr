"""Trava a normalizacao pela unidade de cotacao do COTAHIST.

Bug real, achado na auditoria de 10/09/2026: o COTAHIST cota parte da base por LOTE DE
MIL acoes, e o campo `fator_cotacao` diz qual. Nada no pipeline dividia por ele.

Verificado na base inteira antes de mexer: a mediana de
`fechamento / (volume/quantidade)` e EXATAMENTE igual ao fator_cotacao em cada faixa
(1, 100, 1.000, 10.000, 1e6). Ou seja, o campo nao e decorativo -- ele e a unidade.

238 papeis do painel atravessam uma virada de unidade, quase todos entre 2005 e 2007,
quando a B3 migrou de cotacao por-mil para por-acao: LREN3, ELET3, SBSP3, CMIG4, BRKM5,
CPLE6, PCAR4, AMBV4, CESP6, ALPA4.

O dano nao era so de nivel de preco. Como a migracao de unidade veio quase sempre junto
com um GRUPAMENTO, a razao cotada mostrava o efeito LIQUIDO dos dois, e o detector lia um
evento que nao existiu.
"""
from __future__ import annotations

import pytest

from master.eventos import (DENOMINADOR_MAXIMO, PRECO_MINIMO_CONFIAVEL,
                            TOLERANCIA_COM_EVIDENCIA, fracao_mais_proxima)

# (ticker, preco cotado anterior, fator_cotacao anterior, preco cotado no dia ex)
# Todos com fator_cotacao 1 no dia ex -- e a migracao para cotacao por acao.
VIRADAS_REAIS = [
    ("CMIG4", 79.56, 1000, 39.40),
    ("ELET3", 47.50, 1000, 24.40),
    ("SBSP3", 315.00, 1000, 39.20),
    ("BRKM5", 88.85, 1000, 22.90),
    ("LREN3", 60.02, 1000, 38.50),
]


@pytest.mark.parametrize("ticker,cotado_ant,fatcot_ant,cotado", VIRADAS_REAIS)
def test_razao_cotada_inventa_evento_que_nao_existiu(ticker, cotado_ant, fatcot_ant, cotado):
    """Sem normalizar, a razao mistura a troca de unidade com o evento real.

    CMIG4 em 04/06/2007 e o caso que revelou o problema: 79,56 -> 39,40 da razao 2,02,
    que casa com 2,0 dentro da tolerancia e vira "desdobramento 2:1" com confianca alta.
    Nao houve desdobramento nenhum. Houve grupamento de ~500:1 no mesmo dia em que a
    cotacao deixou de ser por mil acoes -- e 1000/500 = 2.
    """
    razao_cotada = cotado_ant / cotado
    fator, erro = fracao_mais_proxima(razao_cotada, DENOMINADOR_MAXIMO)
    # O ponto do teste: a leitura ingenua e PLAUSIVEL. E por isso que passava batido.
    assert erro <= TOLERANCIA_COM_EVIDENCIA, (
        f"{ticker}: a razao cotada {razao_cotada:.4f} deveria parecer um evento redondo -- "
        "e essa aparencia e exatamente a armadilha"
    )
    assert fator > 1, f"{ticker}: a leitura ingenua sugere desdobramento"


@pytest.mark.parametrize("ticker,cotado_ant,fatcot_ant,cotado", VIRADAS_REAIS)
def test_normalizado_revela_o_grupamento_verdadeiro(ticker, cotado_ant, fatcot_ant, cotado):
    """Dividindo pelo fator_cotacao, aparece o evento de verdade: um grupamento grande.

    E o erro relativo despenca. Na CMIG4 vai de ~1% (contra o falso 2,0) para 0,045%
    (contra 1/495). Erro dez vezes menor e a evidencia de que esta e a leitura certa --
    grupamento de verdade usa razao redonda, e razao redonda so aparece na unidade certa.
    """
    razao_por_acao = (cotado_ant / fatcot_ant) / cotado
    fator, erro = fracao_mais_proxima(razao_por_acao, DENOMINADOR_MAXIMO)
    assert fator < 1, f"{ticker}: por acao o preco SUBIU, entao e grupamento"
    assert 1 / fator > 50, f"{ticker}: grupamento grande, nao 2:1 (deu 1:{1/fator:.0f})"
    assert erro <= TOLERANCIA_COM_EVIDENCIA


def test_o_corte_de_centavos_vale_sobre_o_preco_COTADO():
    """Onde o tick de R$0,01 morde -- e onde nao morde.

    O balde `preco_de_centavos` existe porque abaixo de R$1 o tick domina: um papel a
    R$0,02 so pode ir a 0,01 ou 0,03, razoes de exatamente 2,0 e 0,667, e fracao redonda
    ali nao prova nada.

    Mas o tick incide sobre a COTACAO. Num papel cotado por mil acoes, R$0,01 de tick
    equivale a R$0,00001 por acao -- o argumento simplesmente nao se aplica. Se o corte
    fosse feito no preco por acao, os 238 papeis cotados por mil cairiam inteiros no
    balde de centavos e o grupamento de 500:1 da CMIG4, o evento mais bem documentado
    dessa faixa, ficaria de fora do ajuste.
    """
    cotado_ant, fatcot = 79.56, 1000
    por_acao = cotado_ant / fatcot

    assert cotado_ant >= PRECO_MINIMO_CONFIAVEL, "a cotacao e confiavel: R$79,56"
    assert por_acao < PRECO_MINIMO_CONFIAVEL, (
        "e o preco por acao e de centavos -- se o corte olhasse para ele, a CMIG4 sairia"
    )
