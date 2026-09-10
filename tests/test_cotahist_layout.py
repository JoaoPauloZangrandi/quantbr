"""Trava o layout do COTAHIST.

Um erro de uma posicao nos offsets nao quebra nada: o parser continua rodando e devolve
numeros errados em silencio. Este teste monta um registro sintetico a partir das
posicoes do manual da B3 -- escritas aqui de forma INDEPENDENTE do modulo, de proposito,
para que mexer no LAYOUT sem querer quebre o teste em vez de corromper o warehouse.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from ingest import cotahist

# (campo, tamanho) na ordem do registro tipo 01, direto do manual da B3. Total = 245.
SPEC_MANUAL = [
    ("tipreg", 2), ("data", 8), ("codbdi", 2), ("ticker", 12), ("tpmerc", 3),
    ("nome_res", 12), ("especi", 10), ("prazot", 3), ("modref", 4),
    ("abertura", 13), ("maxima", 13), ("minima", 13), ("media", 13),
    ("fechamento", 13), ("melhor_compra", 13), ("melhor_venda", 13),
    ("negocios", 5), ("quantidade", 18), ("volume", 18),
    ("preco_exercicio", 13), ("indopc", 1), ("data_venc", 8), ("fator_cotacao", 7),
    ("pontos_exercicio", 13), ("isin", 12), ("dismes", 3),
]


def _monta_registro(valores: dict[str, str]) -> str:
    partes = []
    for campo, tam in SPEC_MANUAL:
        v = valores.get(campo, "")
        # numericos alinham a direita com zeros; texto alinha a esquerda com espacos
        if campo in {"abertura", "maxima", "minima", "media", "fechamento",
                     "melhor_compra", "melhor_venda", "negocios", "quantidade",
                     "volume", "preco_exercicio", "fator_cotacao", "pontos_exercicio"}:
            partes.append(v.rjust(tam, "0"))
        else:
            partes.append(v.ljust(tam))
    linha = "".join(partes)
    assert len(linha) == 245, f"registro montado com {len(linha)} chars, esperado 245"
    return linha


def test_soma_dos_campos_da_245():
    assert sum(t for _, t in SPEC_MANUAL) == 245


def test_layout_do_modulo_bate_com_o_manual():
    """Offsets e tamanhos do modulo tem que ser identicos aos do manual."""
    do_modulo = [(n, tam) for n, _, tam, _ in cotahist.LAYOUT]
    assert do_modulo == SPEC_MANUAL

    pos = 1
    for nome, ini, tam, _ in cotahist.LAYOUT:
        assert ini == pos, f"campo {nome} comeca em {ini}, esperado {pos}"
        pos += tam


def test_parse_extrai_valores_corretos(tmp_path):
    import zipfile

    linha = _monta_registro({
        "tipreg": "01", "data": "20240102", "codbdi": "02", "ticker": "PETR4",
        "tpmerc": "010", "nome_res": "PETROBRAS", "especi": "PN", "modref": "R$",
        "abertura": "3744", "maxima": "3789", "minima": "3740", "media": "3760",
        "fechamento": "3778", "melhor_compra": "3777", "melhor_venda": "3779",
        "negocios": "39280", "quantidade": "23976300", "volume": "90551383800",
        "fator_cotacao": "1", "isin": "BRPETRACNPR6", "dismes": "106",
    })
    cabecalho = "00COTAHIST.2024BOVESPA " .ljust(245)
    rodape = "99COTAHIST.2024BOVESPA ".ljust(245)

    zpath = tmp_path / "COTAHIST_TESTE.ZIP"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("COTAHIST.TXT", "\r\n".join([cabecalho, linha, rodape]).encode("latin-1"))

    df = cotahist.parse(zpath)

    assert len(df) == 1, "header/trailer deveriam ter sido descartados"
    r = df.iloc[0]
    assert r["ticker"] == "PETR4"
    assert r["isin"] == "BRPETRACNPR6"
    assert r["data"] == pd.Timestamp("2024-01-02")
    # v99: as duas ultimas casas sao decimais implicitas
    assert r["abertura"] == pytest.approx(37.44)
    assert r["fechamento"] == pytest.approx(37.78)
    assert r["volume"] == pytest.approx(905_513_838.00)
    assert r["negocios"] == 39280
    assert r["fator_cotacao"] == 1


def test_parse_descarta_o_que_nao_e_mercado_a_vista(tmp_path):
    import zipfile

    vista = _monta_registro({"tipreg": "01", "data": "20240102", "codbdi": "02",
                             "ticker": "VALE3", "tpmerc": "010", "fechamento": "6000",
                             "fator_cotacao": "1", "isin": "BRVALEACNOR0"})
    opcao = _monta_registro({"tipreg": "01", "data": "20240102", "codbdi": "78",
                             "ticker": "VALEA60", "tpmerc": "070", "fechamento": "150",
                             "fator_cotacao": "1", "isin": "BRVALEACNOR0"})
    zpath = tmp_path / "COTAHIST_MIX.ZIP"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("COTAHIST.TXT", "\r\n".join([vista, opcao]).encode("latin-1"))

    df = cotahist.parse(zpath)
    assert list(df["ticker"]) == ["VALE3"]
