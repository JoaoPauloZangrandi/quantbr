"""Trava o detector de eventos nos casos que ja o quebraram.

Todo caso aqui e um bug REAL que aconteceu, nao um cenario imaginado. Os dois primeiros
custaram uma auditoria cada para serem descobertos, e os dois eram silenciosos: o pipeline
continuava rodando e entregando numero errado.
"""
from __future__ import annotations

import pytest

from master.eventos import (DENOMINADOR_MAXIMO, TOLERANCIA_COM_EVIDENCIA,
                           TOLERANCIA_RELATIVA, fracao_mais_proxima)


def _classifica(razao: float) -> tuple[float, bool]:
    fator, erro = fracao_mais_proxima(razao, DENOMINADOR_MAXIMO)
    return fator, (erro == erro and erro <= TOLERANCIA_RELATIVA)


@pytest.mark.parametrize("razao,fator_esperado,descricao", [
    (2.0,     2.0,   "desdobramento 2:1"),
    (1.9793,  2.0,   "PETR4 28/04/2008: 84,30 -> 42,59, desdobramento 2:1 real"),
    (4.0248,  4.0,   "PETR3 01/09/2005, desdobramento 4:1 real"),
    (0.5,     0.5,   "grupamento 1:2"),
    (1.5,     1.5,   "desdobramento 3:2"),
])
def test_evento_verdadeiro_e_aceito(razao, fator_esperado, descricao):
    fator, aceito = _classifica(razao)
    assert aceito, f"deveria aceitar: {descricao}"
    assert fator == pytest.approx(fator_esperado, rel=1e-6)


def test_crash_da_covid_nao_pode_virar_desdobramento():
    """Bug real: com denominador 20, a PETR4 em 09/03/2020 (-29%) foi classificada como
    desdobramento de fator 27/19 = 1,421053 e confianca ALTA. O maior crash da bolsa
    virava evento corporativo na acao mais liquida do pais."""
    _, aceito = _classifica(1.422430)
    assert not aceito, "o crash da COVID nao pode passar como evento de quantidade"


@pytest.mark.parametrize("razao,fator_esperado", [
    (0.02,  0.02),    # grupamento 50:1
    (0.001, 0.001),   # grupamento 1000:1
    (0.10,  0.10),    # grupamento 10:1
])
def test_grupamento_grande_nao_pode_sumir(razao, fator_esperado):
    """Bug real: ao apertar o denominador para 4, Fraction(0,02).limit_denominator(4)
    passou a devolver ZERO e o evento desaparecia. A ASTA4 em 06/04/2005 (R$405 ->
    R$20.250, grupamento 50:1) entrou no agregado como retorno de +4.900%."""
    fator, aceito = _classifica(razao)
    assert aceito, "grupamento de fator grande tem que ser detectado"
    assert fator == pytest.approx(fator_esperado, rel=1e-6)


def test_simetria_entre_desdobramento_e_grupamento():
    """Razao x e 1/x tem que ser tratadas com o mesmo criterio. Sem isso, o detector
    enxerga um lado do evento e nao o outro."""
    for razao in (2.0, 4.0, 10.0, 50.0):
        _, aceito_direto = _classifica(razao)
        _, aceito_inverso = _classifica(1.0 / razao)
        assert aceito_direto == aceito_inverso, f"assimetria em {razao}"


@pytest.mark.parametrize("razao", [1.4224, 1.62, 1.88, 0.55])
def test_razoes_claramente_nao_redondas_sao_rejeitadas(razao):
    """Se alguma destas passar, o denominador maximo voltou a ficar frouxo."""
    _, aceito = _classifica(razao)
    assert not aceito, f"razao {razao} nao deveria ser aceita como evento"


@pytest.mark.parametrize("razao", [1.31, 1.72])
def test_o_teste_de_fracao_sozinho_nao_basta(razao):
    """Documenta um limite REAL do detector, em vez de fingir que ele nao existe.

    Com denominador 4 e tolerancia de 2%, as faixas aceitas em torno de 4/3, 3/2, 5/3,
    7/4 e 2/1 cobrem perto de metade do intervalo [1,3; 2,0]. Entao 1,31 (a 1,8% de 4/3)
    e 1,72 (a 1,7% de 7/4) PASSAM no teste de fracao -- e passar ali nao significa ser
    evento.

    Quem carrega a discriminacao de verdade sao as confirmacoes de quantidade negociada e
    de volume financeiro, exigidas para a confianca 'alta'. Este teste existe para que
    ninguem leia o teste de fracao como se fosse o detector inteiro.
    """
    _, aceito = _classifica(razao)
    assert aceito, "faixa larga conhecida: a fracao aceita, as confirmacoes e que decidem"


# ---------------------------------------------------------------------------
# Auditoria de 09/09/2026: o detector reprovava desdobramento obvio.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("razao,fator_esperado,descricao", [
    (4.139740, 4.0, "CSAN3 06/05/2021: 89,17 -> 21,54, desdobramento 4:1"),
    (4.115615, 4.0, "KROT3 12/09/2014: 61,94 -> 15,05, desdobramento 4:1"),
    (4.863813, 5.0, "NATU3 31/03/2006: 125,00 -> 25,70, desdobramento 5:1"),
    (3.901478, 4.0, "TRPL4 05/04/2019: 79,20 -> 20,30, desdobramento 4:1"),
    (3.130435, 3.0, "CSNA3 23/01/2008: 144,00 -> 46,00, desdobramento 3:1"),
    (3.834209, 4.0, "LWSA3 01/02/2021: 102,22 -> 26,66, desdobramento 4:1"),
    (4.121951, 4.0, "ORVR3 11/08/2026: 67,60 -> 16,40, desdobramento 4:1"),
])
def test_desdobramento_grande_com_dia_ex_movimentado(razao, fator_esperado, descricao):
    """Bug real: os sete eram descartados, e por dois motivos somados.

    (1) A fracao de denominador 4 roubava o casamento do inteiro -- 4,1397 casava com
    17/4 = 4,25 em vez de 4. (2) A tolerancia de 2% nao cabia o movimento do proprio dia
    ex: o papel desdobra E se mexe, e o erro real fica entre 2,2% e 4,4%.

    Todos tem razao extrema, entao a tolerancia que vale aqui e a com evidencia.
    """
    fator, erro = fracao_mais_proxima(razao, DENOMINADOR_MAXIMO)
    assert fator == pytest.approx(fator_esperado, rel=1e-6), f"fator errado: {descricao}"
    assert erro <= TOLERANCIA_COM_EVIDENCIA, f"deveria aceitar: {descricao}"


@pytest.mark.parametrize("razao,fator_certo,fracao_que_roubava", [
    (4.139740, 4.0, 4.25),   # 17/4
    (4.863813, 5.0, 4.75),   # 19/4
    (3.130435, 3.0, 3.25),   # 13/4
    (3.834209, 4.0, 3.75),   # 15/4
])
def test_fracao_densa_nao_rouba_o_inteiro(razao, fator_certo, fracao_que_roubava):
    """De 3x para cima so vale inteiro. Se esta faixa voltar a aceitar denominador 4,
    o casamento volta para a fracao errada e o erro volta a estourar a tolerancia."""
    fator, _ = fracao_mais_proxima(razao, DENOMINADOR_MAXIMO)
    assert fator == pytest.approx(fator_certo, rel=1e-6)
    assert fator != pytest.approx(fracao_que_roubava, rel=1e-6)


def test_covid_continua_reprovada_com_a_folga_maior():
    """A trava do desenho. Afrouxar a tolerancia de 2% para 5% so e seguro porque a razao
    do crash da COVID na PETR4 (1,4224) erra 5,17% contra 3/2 -- fica de fora nos DOIS
    niveis. Se alguem aumentar a folga alem disso, o maior crash da bolsa volta a entrar
    como desdobramento."""
    _, erro = fracao_mais_proxima(1.422430, DENOMINADOR_MAXIMO)
    assert erro > TOLERANCIA_COM_EVIDENCIA


# ---------------------------------------------------------------------------
# 10/09/2026: a quantidade de acoes da CVM como terceira evidencia.
# ---------------------------------------------------------------------------
# Pesquisa que motivou: a relacao "se as acoes multiplicam por N, o preco divide por N,
# e o valor de mercado nao muda" e o criterio padrao de deteccao de evento de quantidade.
# A contagem de acoes do FRE da CVM e uma SEGUNDA MEDIDA do mesmo fator, vinda de fora da
# B3 -- imune ao tick de R$0,01 e ao movimento do dia ex, que sao os dois erros que
# sobravam no detector.

from master.eventos import TOLERANCIA_ACOES, TOLERANCIA_COM_ACOES


@pytest.mark.parametrize("ticker,fator,erro_preco,razao_acoes,descricao", [
    ("MGLU3", 8.0, 0.052149, 8.813913, "MGLU3 05/09/2017, desdobramento 8:1"),
    ("MGLU3", 8.0, 0.057377, 8.524682, "MGLU3 06/08/2019, desdobramento 8:1"),
    ("CASH3", 6.0, 0.077572, 6.355920, "CASH3 10/09/2021, desdobramento 6:1"),
])
def test_cvm_destrava_evento_que_o_preco_sozinho_nao_provava(
        ticker, fator, erro_preco, razao_acoes, descricao):
    """Os tres eram descartados: o erro de preco ficava acima da tolerancia com evidencia.

    A contagem de acoes confirma o fator por fora, e ai o preco so precisa ser
    aproximadamente consistente -- ele deixa de ser a unica prova.
    """
    confirma = abs(razao_acoes / fator - 1) <= TOLERANCIA_ACOES
    assert confirma, f"{descricao}: a CVM deveria confirmar o fator"
    assert erro_preco <= TOLERANCIA_COM_ACOES, f"{descricao}: deveria passar com a folga da CVM"


@pytest.mark.parametrize("ticker,fator,erro_preco,razao_acoes,descricao", [
    ("AMER3", 4.0, 0.102941, 1.000000, "colapso da Americanas 12/01/2023: -77% REAL"),
    ("PCAR3", 4.0, 0.110587, 1.002538, "cisao do Assai 01/03/2021: nao e desdobramento"),
    ("PETR4", 1.5, 0.051713, 1.000000, "crash da COVID na PETR4 09/03/2020"),
])
def test_a_folga_da_cvm_nao_abre_a_porta_para_queda_real(
        ticker, fator, erro_preco, razao_acoes, descricao):
    """A trava do desenho, e a razao de a folga ser condicional e nao geral.

    Nos tres a quantidade de acoes ficou em 1,00 -- nenhuma emissao aconteceu, porque
    nenhum evento de quantidade aconteceu. Sem confirmacao da CVM nao ha folga, e os tres
    continuam de fora mesmo com erro de preco proximo do limite.

    Se alguem tornar TOLERANCIA_COM_ACOES incondicional, a queda de 77% da Americanas
    volta a ser apagada da serie ajustada.
    """
    confirma = abs(razao_acoes / fator - 1) <= TOLERANCIA_ACOES
    assert not confirma, f"{descricao}: a CVM NAO pode confirmar isso"
