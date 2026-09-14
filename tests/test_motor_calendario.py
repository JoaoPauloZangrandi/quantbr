"""Trava o casamento por MES DE CALENDARIO entre sinal e retorno, e o rotulo da serie.

Os dois bugs que estes testes travam foram achados pelo Codex em 11/09/2026, com painel
sintetico, e sao o mesmo bug visto de dois lados:

  A. `shift(-1)` anda para o proximo REGISTRO do painel, nao para o proximo mes. Bastava
     um mes faltar -- papel que nao negociou, que caiu do filtro de liquidez, ou mes sem
     sinal -- para o motor entregar o retorno de dois meses adiante como se fosse o do mes
     seguinte. No exemplo dele, 2% viravam 30%.

  B. a serie saia indexada pelo mes de FORMACAO carregando o retorno do mes SEGUINTE, e
     `_metricas` faz `rf.reindex(r.index)`. Resultado: CDI de janeiro descontado de um
     retorno de fevereiro -- em todo Sharpe ja publicado, inclusive o do benchmark.

Nao tocam o warehouse: painel e CDI sao injetados.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from estrategias import motor


def _painel(meses: list[str], retornos: list[float], n: int = 4) -> pd.DataFrame:
    """Painel plano: `n` papeis, todos com o mesmo retorno em cada mes."""
    return pd.DataFrame([{
        "cnpj": f"{i:014d}", "ticker": f"T{i}", "nome": f"EMPRESA {i}",
        "ano_mes": mes, "retorno": retornos[j],
        "volume_mediano": 1e6, "custo_roundtrip": 0.01, "capacidade_dia": 100.0,
        "valor_mercado_empresa": 5e8, "pregoes_no_mes": 20,
        "motivo_saida": None, "retorno_delisting": np.nan,
    } for j, mes in enumerate(meses) for i in range(n)])


def _serie_bruta(painel: pd.DataFrame, sinal: pd.DataFrame | None = None,
                 par: motor.Parametros | None = None) -> dict:
    """Roda o motor e devolve {mes_do_indice: retorno_bruto}, sem DB e sem ledger."""
    if sinal is None:
        sinal = painel[["cnpj", "ano_mes"]].assign(sinal=1.0)
    # `_metricas` e chamado duas vezes, bruto e depois liquido. Queremos o BRUTO: o custo
    # nao tem nada a ver com o que estes testes travam, e deixa-lo entrar so esconde o mes.
    capturado = []
    original = motor._metricas

    def espiao(r, rf=None):
        capturado.append(r.to_dict())
        return original(r, rf)

    rf_zero = pd.Series(0.0, index=sorted(painel["ano_mes"].unique()))
    with patch.object(motor, "_risk_free_mensal", return_value=rf_zero), \
         patch.object(motor, "_metricas", side_effect=espiao), \
         patch.object(motor.warehouse, "connect", side_effect=AssertionError("DB proibido")):
        motor.rodar(sinal, par or motor.Parametros(n_papeis=2), registrar=False,
                    painel=painel, nome="TESTE_CALENDARIO")
    return capturado[0]


def test_lacuna_de_sinal_nao_puxa_o_retorno_de_dois_meses_adiante():
    """O caso do Codex. Fevereiro rende 2%, marco rende 30%.

    Sem o sinal de fevereiro, o motor nao pode substituir fevereiro por marco: quem formou
    em janeiro colheu 2%, e so. Antes da correcao esta linha dava 0,30.
    """
    px = _painel(["2020-01", "2020-02", "2020-03"], [0.0, 0.02, 0.30])
    completo = _serie_bruta(px)
    esparso = _serie_bruta(px, px.loc[px["ano_mes"] != "2020-02", ["cnpj", "ano_mes"]]
                           .assign(sinal=1.0))
    assert completo["2020-02"] == 0.02
    assert esparso["2020-02"] == 0.02, "lacuna de sinal voltou a puxar marco para janeiro"


def test_lacuna_no_painel_nao_forma_mes_em_vez_de_inventar_o_retorno():
    """Painel com janeiro e marco, sem fevereiro. O motor nao pode formar nada.

    Realizar marco exigiria formar em fevereiro, e fevereiro nao existe no painel. A
    resposta honesta e nenhum mes -- antes da correcao, janeiro recebia os 30% de marco.
    """
    px = _painel(["2020-01", "2020-02", "2020-03"], [0.0, 0.02, 0.30])
    sem_fevereiro = px[px["ano_mes"] != "2020-02"]
    sinal = sem_fevereiro[["cnpj", "ano_mes"]].assign(sinal=1.0)
    rf_zero = pd.Series(0.0, index=sorted(px["ano_mes"].unique()))
    with patch.object(motor, "_risk_free_mensal", return_value=rf_zero),          patch.object(motor.warehouse, "connect", side_effect=AssertionError("DB proibido")):
        r = motor.rodar(sinal, motor.Parametros(n_papeis=2), registrar=False,
                        painel=sem_fevereiro, nome="TESTE_CALENDARIO")
    assert "erro" in r, f"formou carteira sem retorno observado: {r}"


def test_papel_com_lacuna_fica_na_carteira_com_hipotese_declarada():
    """Um papel perde fevereiro; os demais nao. Ele NAO sai, e nao herda marco.

    Este teste travava o oposto ate 11/09/2026 -- "papel com lacuna SAI da carteira" -- e
    era o achado E do Codex: quem sai antes da selecao faz a carteira depender de o papel
    existir no futuro, e o 3o colocado herda a vaga do 2o que parou de negociar. A regra
    nova carrega a posicao com a hipotese escrita em `retorno_posicao_presa`.

    O que continua travado, e e o ponto de A: ele nao pode receber os 30% de marco.
    """
    px = _painel(["2020-01", "2020-02", "2020-03"], [0.0, 0.02, 0.30], n=6)
    furado = px[~((px["cnpj"] == f"{0:014d}") & (px["ano_mes"] == "2020-02"))]

    # Default: dinheiro preso, sem ganho nem perda. Carteira de 2 = (0,00 + 0,02) / 2.
    assert _serie_bruta(furado)["2020-02"] == 0.01, "a posicao presa sumiu da carteira"
    # Hipotese oposta: perda total. Mede a sensibilidade de uma escolha que e do analista.
    perda = _serie_bruta(furado, par=motor.Parametros(n_papeis=2,
                                                      retorno_posicao_presa=-1.0))
    assert abs(perda["2020-02"] - (-0.49)) < 1e-12
    # Em nenhuma das duas o papel com lacuna pode colher os 30% de marco.
    assert _serie_bruta(furado)["2020-02"] < 0.30


def test_serie_e_indexada_pelo_mes_em_que_o_retorno_aconteceu():
    """O rotulo tem que ser o mes de realizacao, senao o CDI e descontado do mes errado."""
    px = _painel(["2020-01", "2020-02"], [0.0, 0.02])
    serie = _serie_bruta(px)
    assert list(serie) == ["2020-02"], "serie voltou a ser rotulada pelo mes de formacao"
    assert serie["2020-02"] == 0.02


def test_cdi_descontado_e_o_do_mes_do_retorno():
    """A consequencia de B, medida: com CDI so em fevereiro, o excesso tem que ser zero.

    Formacao em janeiro, retorno de 2% em fevereiro, CDI de 2% em fevereiro e 0% em
    janeiro. Rotulando pela formacao, `rf.reindex` pegava o zero de janeiro e o motor
    declarava 2% de excesso que nao existiu.
    """
    retornos = pd.Series([0.02], index=["2020-02"])
    rf = pd.Series([0.0, 0.02], index=["2020-01", "2020-02"])
    m = motor._metricas(pd.concat([retornos] * 12, ignore_index=False)
                        .set_axis([f"2020-{k:02d}" for k in range(1, 13)]),
                        pd.Series(0.02, index=[f"2020-{k:02d}" for k in range(1, 13)]))
    assert abs(m["retorno_sobre_cdi"]) < 1e-9, "retorno igual ao CDI tem excesso zero"
    assert motor._mes_seguinte(["2020-01", "2020-12"]).tolist() == ["2020-02", "2021-01"]
    assert rf.reindex(retornos.index).iloc[0] == 0.02
