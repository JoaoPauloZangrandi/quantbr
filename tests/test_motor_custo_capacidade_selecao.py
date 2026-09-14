"""Trava os quatro achados que o Codex deixou abertos em 11/09/2026: C, D, E e F.

Os numeros esperados aqui nao sao invencao deste teste -- sao os mesmos casos sinteticos
que o Codex montou em `knowledge/negligenciadas/auditar_motor_sintetico.py` e que
`ANALISE_N01.md` documenta. Cada teste falha se o motor voltar ao comportamento antigo.

  C. rebalanceamento de graca: o retorno bruto e a MEDIA dos papeis, o que supoe voltar a
     peso igual todo mes, mas o custo so era cobrado de quem entrava e saia. Papel que
     dobrou e ficou era reequilibrado sem pagar. Giro unilateral devido: 16,67%.

  D. capacidade somada em vez do gargalo: R$50.500 reportados contra R$1.000 reais, 50,5x.

  E. selecao dependente de disponibilidade futura: o papel de maior sinal que parou de
     negociar sumia da cross-section antes do ranking e o seguinte herdava a vaga.
     (Travado em `test_motor_calendario.py`, que e onde a regra de calendario vive.)

  F. custo pela MEDIANA dos papeis mantidos, e nao pelo spread de cada ordem. A mediana e
     o numero que esconde o problema: quem entra e sai de carteira de small cap e a ponta
     cara, e os papeis mantidos nao sabem disso.

Nenhum deles toca o warehouse: painel e CDI sao injetados.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from estrategias import motor

MESES = ["2020-01", "2020-02", "2020-03"]


def _painel(n: int, *, retorno=None, custo=None, capacidade=None, volume=None,
            meses: list[str] | None = None) -> pd.DataFrame:
    """Painel sintetico com um valor por (papel, mes) para o que cada teste precisa mexer.

    `retorno`, `custo`, `capacidade` e `volume` sao funcoes (i, mes) -> valor.
    """
    meses = meses or MESES
    retorno = retorno or (lambda i, m: 0.0)
    custo = custo or (lambda i, m: 0.002)
    capacidade = capacidade or (lambda i, m: 1e6)
    volume = volume or (lambda i, m: 1e6)
    return pd.DataFrame([{
        "cnpj": f"{i:014d}", "ticker": f"T{i}", "nome": f"EMPRESA {i}",
        "ano_mes": m, "retorno": retorno(i, m),
        "volume_mediano": volume(i, m), "custo_roundtrip": custo(i, m),
        "capacidade_dia": capacidade(i, m), "valor_mercado_empresa": 5e8,
        "pregoes_no_mes": 20, "motivo_saida": None, "retorno_delisting": np.nan,
    } for m in meses for i in range(n)])


def _rodar(painel: pd.DataFrame, sinal: pd.DataFrame, par: motor.Parametros) -> dict:
    rf = pd.Series(0.0, index=sorted(painel["ano_mes"].unique()))
    with patch.object(motor, "_risk_free_mensal", return_value=rf), \
         patch.object(motor.warehouse, "connect",
                      side_effect=AssertionError("DB proibido")):
        return motor.rodar(sinal, par, registrar=False, painel=painel, nome="TESTE")


def _sinal_fixo(painel: pd.DataFrame, ordem: dict[str, list[int]]) -> pd.DataFrame:
    """Sinal explicito por mes: `ordem[mes]` vai do melhor papel para o pior."""
    linhas = []
    for mes, papeis in ordem.items():
        for posicao, i in enumerate(papeis):
            linhas.append({"cnpj": f"{i:014d}", "ano_mes": mes,
                           "sinal": float(len(papeis) - posicao)})
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- C
def test_rebalancear_para_peso_igual_custa_giro_de_16_67_por_cento():
    """O caso do Codex: dois papeis, um dobra, e a equalizacao nao era cobrada.

    Comeca 50/50. Um rende +100% e o outro 0: a carteira termina o mes em 2/3 e 1/3.
    Voltar a 50/50 vende 1/6 de um e compra 1/6 do outro -- giro unilateral de 16,67%,
    que o motor antigo reportava como ZERO porque nenhum nome tinha mudado.
    """
    px = _painel(8, retorno=lambda i, m: 1.0 if (i == 0 and m == "2020-02") else 0.0)
    sinal = _sinal_fixo(px, {m: [0, 1, 2, 3, 4, 5, 6, 7] for m in MESES})
    r = _rodar(px, sinal, motor.Parametros(n_papeis=2))

    # Dois meses formam: o primeiro monta a carteira do zero (giro 0,5 -- so a ponta de
    # compra), o segundo so reequilibra (1/6). O motor antigo dava 1,0 e 0,0.
    assert abs(r["giro_medio"] - (0.5 + 1 / 6) / 2) < 1e-12, (
        f"giro medio {r['giro_medio']:.4f}: o rebalanceamento voltou a ser de graca")
    assert r["custo_anual"] > 0, "carteira que nao muda de nome ainda paga para equalizar"


# --------------------------------------------------------------------------- D
def test_capacidade_e_o_gargalo_e_nao_a_soma():
    """R$100 e R$10.000 por dia, cinco pregoes: R$1.000 cabem, nao R$50.500.

    Em peso igual cada posicao recebe K/N, e K/N tem que caber no MENOS liquido. Somar
    responde outra pergunta -- a de uma carteira ponderada por liquidez, que este motor
    nao simula. A razao entre as duas no exemplo do Codex e 50,5x.
    """
    caps = {0: 100.0, 1: 10_000.0}
    px = _painel(8, capacidade=lambda i, m: caps.get(i, 1e9))
    sinal = _sinal_fixo(px, {m: [0, 1, 2, 3, 4, 5, 6, 7] for m in MESES})
    r = _rodar(px, sinal, motor.Parametros(n_papeis=2))

    assert r["capacidade_mediana"] == 2 * 100.0 * motor.DIAS_PARA_MONTAR == 1_000.0
    assert r["capacidade_soma_mediana"] == 10_100.0 * motor.DIAS_PARA_MONTAR == 50_500.0
    assert (r["capacidade_soma_mediana"] / r["capacidade_mediana"]) == 50.5


# --------------------------------------------------------------------------- F
def test_custo_e_o_da_ordem_e_nao_a_mediana_da_carteira():
    """Entra UM papel caro numa carteira de quatro baratos. A mediana nao ve.

    Carteira de 4 papeis a 0,20% de ida e volta. No segundo mes o papel 9, a 10,00%,
    entra no lugar do papel 3. A mediana dos quatro selecionados continua 0,20%, entao o
    motor antigo cobrava 0,25 x 0,20% = 0,05% pela troca. O custo real da ordem e meio
    round-trip de cada ponta: 0,25 x 10,00%/2 + 0,25 x 0,20%/2 = 1,275%.
    """
    caro = {9: 0.10}
    px = _painel(10, custo=lambda i, m: caro.get(i, 0.002))
    sinal = _sinal_fixo(px, {"2020-01": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                             "2020-02": [0, 1, 2, 9, 4, 5, 6, 7, 8, 3],
                             "2020-03": [0, 1, 2, 9, 4, 5, 6, 7, 8, 3]})
    r = _rodar(px, sinal, motor.Parametros(n_papeis=4))

    montagem = 4 * 0.25 * 0.002 / 2           # mes 1: compra os quatro baratos
    troca = (0.25 * 0.10 + 0.25 * 0.002) / 2  # mes 2: vende o barato, compra o caro
    assert abs(r["custo_anual"] - (montagem + troca) / 2 * 12) < 1e-12, (
        "o custo voltou a sair da mediana da carteira em vez do spread de cada ordem")
    # Quanto a mediana subestimava a troca, deixado no registro como numero.
    assert troca / (0.25 * 0.002) > 25


# ----------------------------------------------------- A, a outra metade (liquidez)
def test_papel_que_seca_nao_evapora_da_carteira():
    """Comprado liquido, iliquido no mes seguinte: a perda e da carteira, nao some.

    O filtro de liquidez decide quem ENTRA, e o teste cobra as duas metades disso:

    - o papel 0 esta ILIQUIDO no mes da FORMACAO e portanto nao pode ser comprado, mesmo
      tendo o maior sinal (e mesmo rendendo +50% depois -- o motor nao sabe disso);
    - o papel 1 esta liquido quando e comprado e SECA no mes seguinte. A perda de 50% e
      da carteira. Enquanto o filtro morava no SQL do painel, ele apagava tambem o
      CAMINHO de quem ja tinha sido comprado: a posicao evaporava sem retorno e a
      carteira ficava so com a parte liquida do que ela mesma escolheu -- vies de
      sobrevivencia construido pelo proprio filtro.

    Carteira de dois: entram os papeis 1 e 2, e o mes rende (-50% + 0%) / 2.
    """
    retornos = {(0, "2020-02"): 0.50, (1, "2020-02"): -0.50}
    iliquidos = {(0, "2020-01"), (1, "2020-02")}
    px = _painel(
        8,
        retorno=lambda i, m: retornos.get((i, m), 0.0),
        volume=lambda i, m: 1e4 if (i, m) in iliquidos else 1e6,
    )
    sinal = _sinal_fixo(px, {m: [0, 1, 2, 3, 4, 5, 6, 7] for m in MESES})

    capturado = []
    original = motor._metricas

    def espiao(r, rf=None):
        capturado.append(r.to_dict())
        return original(r, rf)

    with patch.object(motor, "_metricas", side_effect=espiao):
        _rodar(px, sinal, motor.Parametros(n_papeis=2))

    assert capturado[0]["2020-02"] == -0.25, (
        "o papel que secou sumiu do painel e levou a perda junto")
