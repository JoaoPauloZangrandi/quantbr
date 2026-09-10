"""Trava quais codigos BDI entram no painel, e por que.

Bug real, medido em 10/09/2026: o painel filtrava `codbdi = '02'` (lote padrao) e com
isso apagava a empresa exatamente quando ela quebrava. Ao entrar em recuperacao judicial
o papel migra de 02 para 08 no COTAHIST e CONTINUA negociando -- so que fora da base.

Custo medido: 108 papeis truncados, 445 anos de serie perdidos. O caso que resume tudo e
a AMER3: a base parava em 19/01/2023, o dia seguinte a fraude da Americanas, enquanto o
COTAHIST tem o papel ate hoje. Isso e survivorship criado pelo proprio pipeline, e
enviesado PARA CIMA, porque o trecho cortado e justamente a fase de perda.

Os significados vem da tabela oficial "CODBDI TABLE - LIST OF VALUES FOR BDI CODES" do
layout do COTAHIST (B3, revisao 01 de 17/04/2017), nao de suposicao.
"""
from __future__ import annotations

import pytest

from painel import REGIME_POR_BDI, SQL_BDI, SQL_REGIME

# codigo -> (entra no painel?, significado oficial)
TABELA_OFICIAL = {
    "02": (True, "ROUND LOT"),
    "05": (True, "BMFBOVESPA REGULATIONS SANCTION"),
    "06": (True, "STOCKS OF COS. UNDER REORGANIZATION"),
    "07": (True, "EXTRAJUDICIAL RECOVERY"),
    "08": (True, "JUDICIAL RECOVERY"),
    "09": (True, "TEMPORARY ESPECIAL MANAGEMENT"),
    "11": (True, "INTERVENTION"),
    "58": (True, "OTHERS"),
    "10": (False, "RIGHTS AND RECEIPTS -- e outro papel, nao a acao"),
    "12": (False, "REAL ESTATE FUNDS"),
    "14": (False, "INVESTMENT CERTIFICATES / DEBENTURES -- e onde vivem os ETFs"),
    "22": (False, "BONUSES (PRIVATE)"),
    "96": (False, "FACTIONARY -- fracionario duplicaria a serie do mesmo papel"),
}


@pytest.mark.parametrize("codigo,esperado,significado", [
    (c, v[0], v[1]) for c, v in TABELA_OFICIAL.items()
])
def test_codigo_bdi_entra_ou_nao_conforme_decidido(codigo, esperado, significado):
    assert (codigo in REGIME_POR_BDI) is esperado, (
        f"codbdi {codigo} ({significado}): a decisao mudou sem passar por aqui"
    )


def test_recuperacao_judicial_nao_pode_sair_do_painel():
    """O teste que existe por causa da AMER3.

    Se alguem voltar a filtrar so lote padrao, a base recomeca a apagar a empresa no
    momento em que ela quebra -- e o backtest volta a ser otimista por construcao.
    """
    assert REGIME_POR_BDI.get("08") == "recuperacao_judicial"
    assert REGIME_POR_BDI.get("07") == "recuperacao_extrajudicial"


def test_direitos_e_recibos_ficam_de_fora():
    """A regra de admissao, e o unico codigo que reprovou nela.

    So entra o codbdi para o qual, nos tickers que transitam de 02 para ele, o ISIN
    permanece o mesmo e o preco e continuo. Medido: 07, 08, 58 e 05 tem 100% de ISIN
    identico na transicao. O codigo 10 da 0% de ISIN identico e razao de preco mediana de
    0,03 -- nao e o mesmo papel, e admiti-lo colaria dois ativos diferentes na mesma serie.
    """
    assert "10" not in REGIME_POR_BDI


def test_sql_gerado_bate_com_o_mapa():
    """O SQL e derivado do dicionario; se alguem escrever a lista a mao, quebra aqui."""
    for codigo, regime in REGIME_POR_BDI.items():
        assert f"'{codigo}'" in SQL_BDI
        assert f"THEN '{regime}'" in SQL_REGIME
    assert SQL_BDI.startswith("(") and SQL_BDI.endswith(")")
    assert SQL_REGIME.strip().endswith("ELSE 'outro' END")
