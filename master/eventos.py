"""Deteccao de eventos de quantidade (desdobramento, grupamento, bonificacao) direto do COTAHIST.

Por que detectar em vez de so consultar a B3: a B3 apaga o historico de eventos de quem
sai da bolsa (verificado ao vivo: AESB3 e RRRP3 voltam vazios). O COTAHIST nao apaga
ninguem. Como justamente as empresas que morreram sao as que nao podem faltar num
backtest sem survivorship, a fonte completa tem que ser a primaria.

A ideia central: desdobramento deixa uma assinatura EXATA, e e isso que o separa de
noticia ruim.

  Num desdobramento 2:1 o preco cai para exatamente metade -- razao 2,000.
  Numa crise a acao cai 41%, 47%, 52% -- razao 1,69, 1,89, 2,08.

Entao o discriminante nao e o tamanho da queda, e a proximidade de uma razao racional
simples. Duas confirmacoes secundarias entram para reduzir falso positivo:

  quantidade   -- ha mais acoes em circulacao, entao a quantidade negociada sobe junto
  financeiro   -- o volume em reais NAO muda por causa do evento (o mesmo dinheiro
                  comprando mais papeis mais baratos), diferente de um crash, em que o
                  volume financeiro costuma explodir

Nada aqui e calibrado no olho: os limiares sao parametros, e `master/calibracao.py` mede
acerto e erro contra o gabarito da B3 nas empresas em que ele ainda existe.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np
import pandas as pd

import warehouse

# Uma razao de preco so vira candidata a evento se for grande o bastante para nao se
# confundir com oscilacao normal. 1,30 = o papel mudou de patamar em 30% da noite pro dia.
RAZAO_MINIMA = 1.30
# Tolerancia sobre a fracao. Nao pode ser apertada demais: no dia ex o papel tambem
# NEGOCIA, entao o fechamento nao e exatamente o preco anterior dividido pelo fator.
# O valor antigo, 2%, foi calibrado num caso feliz (PETR4 2008: 84,30 -> 42,59, erro de
# 1,03%) e generalizado -- e reprovava desdobramento obvio quando o papel se mexia no dia
# ex. Medido na auditoria de 09/09/2026: CSAN3 4:1 em 06/05/2021 erra 3,49%, KROT3 4:1
# erra 2,89%, CSNA3 3:1 erra 4,35%. Todos ficavam de fora.
TOLERANCIA_RELATIVA = 0.025
# Folga maior, liberada SO quando ha evidencia independente da fracao: razao extrema ou a
# classe irma confirmando no mesmo pregao. Nao vale a folga por confirmacao de quantidade
# ou financeiro, que sao mais fracas -- com 5% solto em razao pequena, queda de 45% perto
# de 7/4 comecaria a passar. O crash da COVID na PETR4 (razao 1,4224, erro 5,17% sobre
# 3/2) continua reprovado nos DOIS niveis; essa e a trava do desenho.
TOLERANCIA_COM_EVIDENCIA = 0.05
# Folga maior ainda, liberada SO quando a quantidade de acoes da CVM confirma o fator.
# A diferenca de natureza justifica: nos outros niveis o preco tem que PROVAR o evento
# sozinho, e a fracao redonda e toda a prova que existe. Aqui o evento ja foi medido por
# fora, numa fonte que nao e a B3 -- ao preco resta so ser aproximadamente consistente.
# Foi o que destravou o desdobramento 8:1 da MGLU3 (erro de preco 5,2% e 5,7%, contagem
# de acoes 8,81 e 8,52) e o 6:1 da CASH3 (erro 7,8%, contagem 6,36).
# A trava continua valendo: AMER3 (queda real, 10,3%), PCAR3 (cisao do Assai, 11,1%) e a
# COVID na PETR4 (5,2%) tem razao de acoes = 1,00 -- nenhuma emissao aconteceu --, entao
# nao ganham a folga e continuam de fora.
TOLERANCIA_COM_ACOES = 0.10
# Denominador maximo da fracao. ESTE PARAMETRO E O CORACAO DO DETECTOR e ja errou feio:
# com denominador 20, as fracoes ficam tao densas que qualquer razao cai a 2% de alguma,
# e o teste de "razao redonda" deixa de testar coisa nenhuma. O caso que pegou o erro foi
# a PETR4 em 09/03/2020 (segunda-feira do crash da COVID, -29%): razao 1,4224, classificada
# como desdobramento de fator 27/19 = 1,421053, confianca alta. Com denominador 4, as
# unicas candidatas perto dali sao 4/3 e 3/2, a 6,6% e 5,3% -- e o crash e rejeitado.
# Desdobramento de verdade usa razao simples: 2:1, 3:1, 4:1, 10:1, 3:2, 5:2.
DENOMINADOR_MAXIMO = 4
# ...mas denominador 4 so faz sentido em razao PEQUENA, e este foi o segundo erro do
# detector. Perto de 4 as fracoes de denominador 4 (13/4, 15/4, 17/4, 19/4) estao
# espacadas de 6%, entao ELAS ROUBAM O CASAMENTO DO INTEIRO VERDADEIRO: 4,1397 casava com
# 17/4 = 4,25 (erro 2,59%) em vez de 4 (erro 3,49%), e 4,8638 casava com 19/4 = 4,75 em
# vez de 5. O erro ficava logo acima da tolerancia e o evento era descartado -- pelo
# motivo errado. Desdobramento grande e sempre inteiro: 3:1, 4:1, 5:1, 10:1, 50:1.
# Razao fracionaria de verdade (3:2, 5:2, 4:3, 7:4) so existe embaixo.
RAZAO_SO_INTEIRA = 3.0
# Dias usados para medir a quantidade tipica antes e depois do evento.
JANELA_QUANTIDADE = 5
# Abaixo deste preco o tick de R$0,01 domina: um papel a R$0,02 so pode ir para 0,01 ou
# 0,03, e essas razoes sao exatamente 2,0 e 0,667. Fracao redonda ali nao e evidencia de
# nada. Nao descartamos essas linhas -- elas ficam marcadas com confianca separada.
#
# ATENCAO: este teste roda sobre o preco COTADO, nao sobre o preco por acao. O tick de
# R$0,01 incide sobre a cotacao, e quando o papel e cotado por lote de mil o tick vale
# R$0,00001 por acao -- o argumento do tick simplesmente nao se aplica ali. Aplicar o
# corte ao preco por acao jogaria os 238 papeis cotados por mil (CMIG4, ELET3, SBSP3,
# LREN3, BRKM5...) inteiros no balde de centavos, e o grupamento de 500:1 da CMIG4, que
# e o evento mais bem documentado dessa faixa, ficaria de fora do ajuste.
# Tolerancia para casar o fator de preco com a variacao da QUANTIDADE DE ACOES da CVM.
# Larga de proposito (15%): a contagem anual do FRE mistura o evento com emissao, recompra
# e conversao ocorridas no mesmo ano, entao ela nunca bate exato. O que ela oferece nao e
# precisao, e INDEPENDENCIA -- vem da CVM, nao do preco, e por isso nao sofre nem do tick
# de R$0,01 nem do movimento do dia ex, que sao as duas fontes de erro do detector.
# Medido nos casos que o preco sozinho nao provava: MGLU3 8,81 e 8,53 (desdobramento 8:1
# reprovado por 5,2% de erro), CASH3 6,36 (6:1 reprovado por 7,8%), TRPL4 4,000 exato,
# IRBR3 3,000 exato.
TOLERANCIA_ACOES = 0.15

PRECO_MINIMO_CONFIAVEL = 1.00


@dataclass(frozen=True)
class Parametros:
    razao_minima: float = RAZAO_MINIMA
    tolerancia: float = TOLERANCIA_RELATIVA
    tolerancia_com_evidencia: float = TOLERANCIA_COM_EVIDENCIA
    denominador_maximo: int = DENOMINADOR_MAXIMO
    razao_so_inteira: float = RAZAO_SO_INTEIRA
    tolerancia_acoes: float = TOLERANCIA_ACOES
    tolerancia_com_acoes: float = TOLERANCIA_COM_ACOES
    janela: int = JANELA_QUANTIDADE
    preco_minimo: float = PRECO_MINIMO_CONFIAVEL


def fracao_mais_proxima(x: float, denominador_maximo: int,
                        razao_so_inteira: float = RAZAO_SO_INTEIRA) -> tuple[float, float]:
    """Fracao simples mais proxima de x e o erro relativo.

    Usa a expansao em fracao continua (Fraction.limit_denominator), que devolve a melhor
    aproximacao racional com denominador limitado -- exatamente a nocao de "razao redonda"
    que separa desdobramento de queda de mercado.

    O denominador permitido depende da FAIXA da razao (ver RAZAO_SO_INTEIRA): de 3x para
    cima, so inteiro. Sem isso, a malha densa de fracoes com denominador 4 rouba o
    casamento do inteiro verdadeiro e o desdobramento e reprovado por um decimo de ponto.

    Armadilha corrigida: para x < 1 nao da para limitar o denominador direto. Um
    grupamento de 50:1 tem razao 0,02, e Fraction(0,02).limit_denominator(4) devolve
    ZERO -- o evento simplesmente desaparecia. Foi o que aconteceu com a ASTA4 em
    06/04/2005 (R$405 -> R$20.250), que entrou no agregado como retorno de +4.900%.
    A saida e aproximar o INVERSO e inverter de volta: assim 2:1 e 1:2 sao tratados com
    a mesma regra, que e o que a simetria do evento exige.
    """
    if not np.isfinite(x) or x <= 0:
        return (np.nan, np.nan)
    # A simetria exige olhar sempre o lado >= 1 e devolver invertido no fim.
    lado = x if x >= 1 else 1.0 / x
    denom = 1 if lado >= razao_so_inteira else denominador_maximo
    if x >= 1:
        valor = float(Fraction(x).limit_denominator(denom))
    else:
        inverso = float(Fraction(1.0 / x).limit_denominator(denom))
        valor = 1.0 / inverso if inverso else 0.0
    if valor == 0:
        return (np.nan, np.nan)
    return valor, abs(x - valor) / valor


def _razao_de_acoes(con) -> pd.DataFrame:
    """Variacao ano a ano da quantidade de acoes, por ticker, a partir do FRE da CVM.

    A ideia e a mais simples que existe em evento de quantidade e vale a pena escrever:
    desdobramento nao cria valor, so reparte. Se o numero de acoes multiplica por 8, o
    preco divide por 8 -- o valor de mercado nao muda. Entao a contagem de acoes e uma
    SEGUNDA MEDIDA do mesmo fator, e ela vem de outra fonte (a CVM), imune aos dois erros
    que atrapalham o preco: o tick de R$0,01 em papel de centavos e o movimento do proprio
    dia ex.

    Limite honesto: o FRE e ANUAL, entao esta razao mistura o evento com emissao, recompra
    e conversao do mesmo ano, e nao data o evento. Serve para CONFIRMAR um candidato que o
    preco ja apontou -- nunca para criar um evento sozinha.

    A janela e de dois anos (o do evento e o seguinte) porque a data de referencia do FRE
    nao coincide com a data ex, e um evento de dezembro aparece no formulario do ano
    seguinte.
    """
    if not (warehouse.table_exists(con, "cvm_capital_social")
            and warehouse.table_exists(con, "master_ticker")):
        return pd.DataFrame(columns=["ticker", "ano", "razao_acoes"])
    return con.execute("""
        WITH a AS (
            SELECT lpad(regexp_replace(CNPJ_Companhia, '[^0-9]', '', 'g'), 14, '0') AS cnpj,
                   ano_fre,
                   arg_max(Quantidade_Total_Acoes, Versao) AS qtd
            FROM cvm_capital_social
            WHERE Quantidade_Total_Acoes > 0
            GROUP BY 1, 2
        ),
        r AS (
            SELECT cnpj, ano_fre,
                   qtd / nullif(lag(qtd) OVER (PARTITION BY cnpj ORDER BY ano_fre), 0)
                     AS razao_acoes
            FROM a
        ),
        t AS (
            SELECT DISTINCT ticker,
                   lpad(regexp_replace(cnpj, '[^0-9]', '', 'g'), 14, '0') AS cnpj
            FROM master_ticker WHERE cnpj IS NOT NULL
        )
        SELECT t.ticker, r.ano_fre AS ano, r.razao_acoes
        FROM r JOIN t USING (cnpj)
        WHERE r.razao_acoes IS NOT NULL
    """).df()


def _serie_por_ticker(con) -> pd.DataFrame:
    """Serie por ticker com o preco POR ACAO, nao o preco cotado.

    O COTAHIST cota alguns papeis por LOTE DE MIL, e o campo `fator_cotacao` diz qual.
    Verificado na base inteira: a mediana de `fechamento / (volume/quantidade)` e
    exatamente igual ao fator_cotacao em cada faixa (1, 100, 1.000, 10.000, 1e6).

    Sem dividir, a razao de preco mistura DOIS eventos e o detector le o resultado
    liquido. Caso concreto -- CMIG4 em 04/06/2007: o preco cotado cai de 79,56 para
    39,40, razao 2,02, e o detector conclui "desdobramento 2:1". Nao houve desdobramento
    nenhum: houve um GRUPAMENTO de ~500:1 no mesmo dia em que a cotacao passou de por-mil
    para por-acao, e 1000/500 = 2. Por acao o preco foi de R$0,0796 para R$39,40.

    Numericamente o ajuste pelo fator liquido ate acerta o retorno, mas o evento fica com
    tipo e fator errados -- e a contagem de acoes, que vem da CVM em acoes de verdade,
    passa a nao bater com o preco. 238 papeis do painel atravessam uma virada dessas.
    """
    return con.execute("""
        SELECT ticker, data,
               fechamento / fator_cotacao AS fechamento,
               fechamento                  AS fechamento_cotado,
               quantidade, volume, fator_cotacao, isin
        FROM b3_cotahist
        WHERE codbdi IN ('02','05','06','07','08','09','11','58')
          AND fechamento > 0 AND tpmerc = '010'
          AND fator_cotacao > 0
        ORDER BY ticker, data
    """).df()


def detectar(par: Parametros | None = None) -> pd.DataFrame:
    par = par or Parametros()
    with warehouse.connect(read_only=True) as con:
        df = _serie_por_ticker(con)
        acoes = _razao_de_acoes(con)

    g = df.groupby("ticker", sort=False)
    df["fech_ant"] = g["fechamento"].shift(1)
    df["data_ant"] = g["data"].shift(1)
    df["fator_cot_ant"] = g["fator_cotacao"].shift(1)
    df["fech_cotado_ant"] = g["fechamento_cotado"].shift(1)

    # Razao de preco: >1 sugere desdobramento (preco caiu), <1 sugere grupamento.
    df["razao_preco"] = df["fech_ant"] / df["fechamento"]

    # Quantidade tipica antes e depois. Mediana, nao media: um unico pregao atipico
    # perto do evento nao pode decidir a classificacao.
    qtd = g["quantidade"]
    df["qtd_antes"] = qtd.transform(
        lambda s: s.shift(1).rolling(par.janela, min_periods=2).median())
    df["qtd_depois"] = qtd.transform(
        lambda s: s.iloc[::-1].rolling(par.janela, min_periods=2).median().iloc[::-1])
    df["razao_quantidade"] = df["qtd_depois"] / df["qtd_antes"]

    vol = g["volume"]
    df["fin_antes"] = vol.transform(
        lambda s: s.shift(1).rolling(par.janela, min_periods=2).median())
    df["fin_depois"] = vol.transform(
        lambda s: s.iloc[::-1].rolling(par.janela, min_periods=2).median().iloc[::-1])
    df["razao_financeiro"] = df["fin_depois"] / df["fin_antes"]

    salto = df["razao_preco"].where(
        (df["razao_preco"] >= par.razao_minima) | (df["razao_preco"] <= 1 / par.razao_minima)
    )
    cand = df[salto.notna()].copy()

    aprox = cand["razao_preco"].map(
        lambda x: fracao_mais_proxima(x, par.denominador_maximo, par.razao_so_inteira))
    cand["fator_sugerido"] = [a[0] for a in aprox]
    cand["erro_relativo"] = [a[1] for a in aprox]

    # RAZAO EXTREMA -- dispensa as confirmacoes, e precisa dispensar.
    # Acao nao triplica nem cai a um terco num pregao por motivo de mercado. Quando a
    # razao e extrema E redonda, o preco ja decidiu sozinho.
    # Mais: as confirmacoes de quantidade e financeiro NAO SE APLICAM a esses casos.
    # Depois de um grupamento de 40:1 o papel muda de regime de liquidez, e a quantidade
    # deixa de escalar pelo fator. Exigir a confirmacao ali reprova o evento pelo motivo
    # errado. O caso que mostrou isso foi a BRPR3 em 24/02/2023 (R$5,95 -> R$236,52):
    # erro relativo de 0,003% contra 1/39,75, e mesmo assim rebaixada para 'baixa' e
    # deixada de fora do ajuste, mantendo um retorno falso de +3.875% no painel.
    cand["razao_extrema"] = (cand["razao_preco"] >= 3.0) | (cand["razao_preco"] <= 1 / 3.0)

    # CONFIRMACAO CRUZADA ENTRE CLASSES -- o sinal mais forte que existe aqui, e o unico
    # que nao depende de fonte externa nenhuma.
    # Uma empresa com ON e PN desdobra as duas ao mesmo tempo, pelo mesmo fator. Entao o
    # evento aparece no MESMO pregao, com a MESMA razao, em ITUB3 e ITUB4, em POMO3 e
    # POMO4, em FESA3 e FESA4. Movimento de mercado nao faz isso: as duas classes caem
    # juntas, mas nunca na mesma razao redonda exata.
    # Isso importa porque o gabarito da B3 e esparso (351 de 613 emissores com resposta
    # 'ok' tem ZERO evento registrado), entao "nao esta na B3" nao e prova de erro. A
    # confirmacao cruzada da evidencia interna, medida no proprio dado.
    cand["emissor"] = cand["isin"].str.slice(2, 6)
    chave = ["emissor", "data", "fator_sugerido"]
    classes = cand.groupby(chave)["ticker"].transform("nunique")
    cand["classes_confirmam"] = classes > 1

    # MUDANCA DE UNIDADE DE COTACAO -- evidencia independente, e estava sendo calculada
    # e jogada fora. A B3 migrou a cotacao de por-mil para por-acao entre 2005 e 2007, e
    # a empresa trocava de unidade PORQUE tinha acabado de agrupar acoes: os dois eventos
    # vem juntos por construcao. Isso e evidencia que nao sai da razao de preco, entao
    # entra no mesmo nivel de `classes_confirmam`.
    # Nao ha risco de falso positivo por essa via: se a unidade mudasse SEM evento, o
    # preco por acao seria continuo, a razao ficaria perto de 1 e a linha nem chegaria a
    # ser candidata (RAZAO_MINIMA = 1,30).
    # O caso que revelou: CBMA4 em 02/07/2007, R$0,325 -> R$0,65 por acao, razao 0,5 com
    # erro ZERO -- grupamento 2:1 obvio, rebaixado a 'baixa' porque a quantidade nao
    # confirmou, e o salto de +100% ficava na serie.
    cand["fator_cotacao_mudou"] = cand["fator_cotacao"] != cand["fator_cot_ant"]

    # CONFIRMACAO PELA QUANTIDADE DE ACOES (CVM). A terceira evidencia independente do
    # preco, e a unica que vem de fora da B3. Desdobramento nao cria valor: se o numero de
    # acoes multiplica por 8, o preco divide por 8. Entao a contagem e uma segunda medida
    # do mesmo fator -- e ela nao sofre do tick de R$0,01 nem do movimento do dia ex, que
    # sao justamente os dois erros que sobraram no detector.
    if acoes.empty:
        cand["razao_acoes"] = np.nan
    else:
        cand["ano"] = pd.to_datetime(cand["data"]).dt.year
        # Janela de dois anos: a data de referencia do FRE nao coincide com a data ex, e
        # evento de dezembro aparece no formulario do ano seguinte.
        # Dentro da janela, fica a razao MAIS PROXIMA do fator sugerido. Nao e escolher
        # o que da certo: o FRE nao data o evento, entao "houve uma variacao de acoes
        # compativel na janela?" e a pergunta que a fonte consegue responder. Ela confirma
        # um candidato que o preco ja apontou; nunca cria evento sozinha.
        melhor, erro_melhor = None, None
        for desloc in (0, 1):
            tmp = acoes.copy()
            tmp["ano"] = tmp["ano"] - desloc
            j = cand[["ticker", "ano"]].merge(tmp, on=["ticker", "ano"], how="left")
            r = j["razao_acoes"].values
            e = np.abs(r / cand["fator_sugerido"].values - 1)
            if melhor is None:
                melhor, erro_melhor = r, e
            else:
                troca = np.less(e, erro_melhor, where=~np.isnan(e), out=np.zeros_like(e, dtype=bool))
                melhor = np.where(troca, r, melhor)
                erro_melhor = np.where(troca, e, erro_melhor)
        cand["razao_acoes"] = melhor
    cand["acoes_confirmam"] = (
        (cand["razao_acoes"] / cand["fator_sugerido"] - 1).abs() <= par.tolerancia_acoes
    ).fillna(False)

    # TOLERANCIA EM DOIS NIVEIS. A folga maior so vale onde ha evidencia que NAO vem da
    # propria fracao -- razao extrema ou classe irma no mesmo pregao. Onde a razao e
    # pequena e nada corrobora, continua valendo o criterio apertado, que e o que mantem
    # queda de mercado do lado de fora.
    tolerancia = np.where(
        cand["razao_extrema"] | cand["classes_confirmam"] | cand["fator_cotacao_mudou"],
        par.tolerancia_com_evidencia, par.tolerancia)
    # A confirmacao pela CVM manda em cima de qualquer outra: e a unica medida do fator
    # que nao vem do preco.
    tolerancia = np.where(cand["acoes_confirmam"], par.tolerancia_com_acoes, tolerancia)
    cand["tolerancia_usada"] = tolerancia
    cand["razao_redonda"] = cand["erro_relativo"] <= tolerancia
    # Num evento de quantidade, a quantidade negociada acompanha o fator de perto. A folga
    # anterior (0,4x a 2,5x) era larga demais e deixava passar o crash da COVID na PETR4,
    # onde a quantidade subiu 2,38x contra um "fator" de 1,42 -- razao 1,68, aceita.
    esperado = cand["fator_sugerido"]
    cand["quantidade_confirma"] = (cand["razao_quantidade"] / esperado).between(0.60, 1.80)
    # ... enquanto o volume FINANCEIRO deve seguir parecido: o evento nao cria nem
    # destroi dinheiro. Num crash de verdade o financeiro costuma explodir.
    cand["financeiro_estavel"] = cand["razao_financeiro"].between(0.40, 2.50)
    cand["preco_confiavel"] = cand["fech_cotado_ant"] >= par.preco_minimo

    # QUANDO A EVIDENCIA SUPERA O ARGUMENTO DO TICK.
    # `preco_confiavel` entra como AND obrigatorio em todos os ramos, e por isso veta
    # sozinho -- o mesmo defeito estrutural que `razao_redonda` tinha antes de 09/09.
    # O argumento do tick e probabilistico: a R$0,38 de cotacao, o passo de R$0,01
    # produz razoes redondas por acidente. Mas ele so cobre razao PEQUENA. Nao existe
    # artefato de tick que gere razao de 1:900 com erro de 0,03% e as duas classes da
    # mesma empresa concordando no mesmo pregao.
    # Casos que revelaram: JBDU3 e JBDU4 em 30/04/2007, TEKA3 e TEKA4 em 01-05/06/2009 --
    # grupamentos de ~900:1 no balde de centavos, deixando +90.000% de retorno falso.
    # A CVM nao sabe nada sobre o tick de R$0,01 da B3, entao a confirmacao por
    # quantidade de acoes supera o veto de papel de centavos sozinha.
    cand["evidencia_supera_tick"] = (
        cand["razao_extrema"] & (cand["classes_confirmam"] | cand["fator_cotacao_mudou"])
    ) | cand["acoes_confirmam"]
    cand["preco_ok"] = cand["preco_confiavel"] | cand["evidencia_supera_tick"]

    cand["tipo_sugerido"] = np.where(cand["fator_sugerido"] > 1, "desdobramento", "grupamento")

    cond = [
        # Confirmacao entre classes basta sozinha: e evidencia mais forte que quantidade
        # ou financeiro, porque nao ha mecanismo de mercado que a produza por acaso.
        cand["razao_redonda"] & cand["preco_ok"] & cand["acoes_confirmam"],
        cand["razao_redonda"] & cand["preco_ok"] & cand["classes_confirmam"],
        cand["razao_redonda"] & cand["preco_ok"] & cand["fator_cotacao_mudou"],
        cand["razao_redonda"] & cand["preco_ok"] & cand["razao_extrema"],
        (cand["razao_redonda"] & cand["preco_ok"]
         & cand["quantidade_confirma"] & cand["financeiro_estavel"]),
        (cand["razao_redonda"] & cand["preco_ok"]
         & (cand["quantidade_confirma"] | cand["financeiro_estavel"])),
        cand["razao_redonda"] & cand["preco_ok"],
        # Papel de centavos: a razao redonda pode ser artefato do tick de R$0,01.
        # Fica separado em vez de somado ao resto, para nunca virar "evento" por engano.
        cand["razao_redonda"],
    ]
    cand["confianca"] = np.select(
        cond, ["alta", "alta", "alta", "alta", "alta", "media", "baixa",
               "preco_de_centavos"],
        default="descartado")

    cols = ["ticker", "isin", "data", "data_ant", "fech_ant", "fechamento",
            "fech_cotado_ant", "fator_cotacao",
            "razao_preco", "fator_sugerido", "erro_relativo", "razao_quantidade",
            "razao_financeiro", "tolerancia_usada", "razao_redonda", "quantidade_confirma",
            "financeiro_estavel", "preco_confiavel", "preco_ok",
            "evidencia_supera_tick", "razao_acoes", "acoes_confirmam",
            "classes_confirmam", "razao_extrema",
            "fator_cotacao_mudou",
            "tipo_sugerido", "confianca"]
    return cand[cols].reset_index(drop=True)


def gravar(df: pd.DataFrame) -> int:
    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS eventos_detectados")
        con.register("_ev", df)
        con.execute("CREATE TABLE eventos_detectados AS SELECT * FROM _ev")
        con.unregister("_ev")
    return len(df)


if __name__ == "__main__":
    ev = detectar()
    n = gravar(ev)
    print(f"{n:,} candidatos a evento de quantidade")
    print()
    print(ev["confianca"].value_counts().to_string())
    print()
    print("por tipo (so confianca alta):")
    print(ev[ev["confianca"] == "alta"]["tipo_sugerido"].value_counts().to_string())
