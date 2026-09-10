"""Trava as duas propriedades que separam backtest de ilusao.

O motor de backtest tem uma responsabilidade acima de todas: nao deixar informacao do
futuro entrar. O jeito de provar isso nao e ler o codigo, e construir um sinal que SO
poderia funcionar com look-ahead e verificar que ele nao funciona.

Os testes rodam sobre dado sintetico injetado; nao tocam o warehouse.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estrategias import motor


def _painel_sintetico(n_papeis: int = 60, meses: int = 40, semente: int = 42) -> pd.DataFrame:
    """Retornos ALEATORIOS, sem estrutura nenhuma. Qualquer alfa aqui e artefato."""
    rng = np.random.default_rng(semente)
    linhas = []
    for i in range(n_papeis):
        for m in range(meses):
            linhas.append({
                "cnpj": f"{i:014d}",
                "ticker": f"AAA{i}",
                "nome": f"EMPRESA {i}",
                "ano_mes": f"20{10 + m // 12:02d}-{m % 12 + 1:02d}",
                "retorno": float(rng.normal(0.01, 0.08)),
                "volume_mediano": 1e7,
                "custo_roundtrip": 0.004,
                "capacidade_dia": 1e6,
                "valor_mercado_empresa": 1e9,
                "pregoes_no_mes": 21,
                "motivo_saida": None,
                "retorno_delisting": np.nan,
            })
    return pd.DataFrame(linhas)


def test_sinal_que_ve_o_mes_corrente_nao_pode_lucrar():
    """O teste central do motor, e o mais severo que existe para ele.

    O sinal e o retorno DO PROPRIO MES -- previsao perfeita do presente. Se o motor
    usasse o retorno do mes do sinal, isto renderia uma fortuna: seria escolher os 20
    melhores papeis depois de saber quais foram. Como o motor usa o mes SEGUINTE, e os
    retornos sao aleatorios, o resultado tem que ficar perto de zero.

    Se este teste passar a dar retorno alto, alguem removeu o `shift(-1)`.
    """
    px = _painel_sintetico()
    sinal = px[["cnpj", "ano_mes", "retorno"]].rename(columns={"retorno": "sinal"})
    r = motor.rodar(sinal, motor.Parametros(mes_inicial="2010-01", mes_final="2013-12"),
                    nome="teste_look_ahead", registrar=False, painel=px)
    assert "erro" not in r, r
    anual = r["bruto"]["retorno_anual"]
    assert abs(anual) < 0.35, (
        f"retorno anual de {anual:.1%} com sinal do proprio mes e retorno aleatorio -- "
        "o motor esta usando o mes do sinal, nao o seguinte"
    )


def test_sinal_que_ve_o_mes_seguinte_lucra_muito():
    """A contraprova. Sem ela, o teste acima passaria mesmo com o motor quebrado.

    Aqui o sinal e o retorno do mes SEGUINTE -- look-ahead deliberado. Tem que render
    absurdamente. Se NAO render, o motor nao esta casando sinal e retorno de jeito nenhum,
    e o teste anterior estaria passando por vacuidade.
    """
    px = _painel_sintetico()
    futuro = px.sort_values(["cnpj", "ano_mes"]).copy()
    futuro["sinal"] = futuro.groupby("cnpj")["retorno"].shift(-1)
    sinal = futuro[["cnpj", "ano_mes", "sinal"]].dropna()
    r = motor.rodar(sinal, motor.Parametros(mes_inicial="2010-01", mes_final="2013-12"),
                    nome="teste_contraprova", registrar=False, painel=px)
    assert r["bruto"]["retorno_anual"] > 1.0, (
        "com look-ahead deliberado o motor deveria render muito; se nao rende, ele nao "
        "esta ligando sinal a retorno"
    )


def test_o_custo_cobrado_cresce_com_o_giro():
    """Estrategia que troca a carteira inteira paga mais que a que nao troca nada.

    Obvio de enunciar e facil de errar: e comum cobrar custo sobre o patrimonio em vez de
    sobre o giro, o que penaliza igualmente quem gira 5% e quem gira 100%.
    """
    px = _painel_sintetico()
    rng = np.random.default_rng(7)
    # Sinal aleatorio a cada mes -> carteira muda muito.
    ruido = px[["cnpj", "ano_mes"]].copy()
    ruido["sinal"] = rng.normal(size=len(ruido))
    giro_alto = motor.rodar(ruido, motor.Parametros(mes_inicial="2010-01", mes_final="2013-12"),
                            nome="giro_alto", registrar=False, painel=px)
    # Sinal fixo por papel -> carteira quase nao muda.
    fixo = px[["cnpj", "ano_mes"]].copy()
    fixo["sinal"] = fixo["cnpj"].astype("category").cat.codes.astype(float)
    giro_baixo = motor.rodar(fixo, motor.Parametros(mes_inicial="2010-01", mes_final="2013-12"),
                             nome="giro_baixo", registrar=False, painel=px)
    assert giro_alto["giro_medio"] > giro_baixo["giro_medio"]
    assert giro_alto["custo_anual"] > giro_baixo["custo_anual"]


def test_custo_que_quebra_e_menor_quando_a_margem_e_menor():
    """`custo_que_quebra` responde "quantas vezes o custo a estrategia aguenta".

    E a pergunta do protocolo: aumente o custo ate quebrar e reporte o limiar. Uma
    estrategia de margem fina quebra com pouco; uma de margem larga aguenta muito.
    """
    serie_folgada = pd.DataFrame({"retorno_bruto": [0.05] * 24, "custo": [0.001] * 24})
    serie_apertada = pd.DataFrame({"retorno_bruto": [0.005] * 24, "custo": [0.004] * 24})
    assert (motor._custo_que_quebra(serie_folgada)
            > motor._custo_que_quebra(serie_apertada))
