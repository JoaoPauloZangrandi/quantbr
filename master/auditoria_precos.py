"""Auditoria das series de preco contra uma referencia externa e independente.

Verificar o ajuste na PETR4 prova que o mecanismo funciona num caso. Nao prova que ele
funciona no mercado inteiro, que e o que importa. Esta auditoria testa no agregado.

A referencia escolhida e o FATOR DE MERCADO DO NEFIN (USP), serie diaria desde 2001.
Ela serve porque foi construida por terceiros, com metodologia publicada, a partir do
mesmo mercado -- entao concordar com ela e evidencia de que o nosso tratamento de evento
corporativo esta certo, e discordar e sinal de problema nosso.

O plano original previa reconstruir o Ibovespa e comparar com o indice oficial. Isso NAO
e possivel de graca: a API de indices da B3 so devolve a carteira vigente, e o parametro
de ano e ignorado (verificado -- pedir 2018 devolve a carteira de hoje). Sem peso
historico nao ha reconstrucao honesta do indice, entao a referencia passa a ser o NEFIN.

O resultado que interessa nao e "a serie ajustada bate bem". E o CONTRASTE: a serie
ajustada tem que bater e a serie CRUA tem que bater mal. Se as duas baterem igual, o
ajuste nao esta fazendo nada e ha algo errado no pipeline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse

# Universo liquido para a carteira de teste. Nao e o universo de pesquisa do fundo -- e
# so um agregado estavel o suficiente para comparar com o fator de mercado.
TOP_LIQUIDEZ = 150
PRECO_MINIMO = 1.00
JANELA_LIQUIDEZ = 252
# Piso ABSOLUTO de liquidez, em reais por dia. So "top N" nao basta e ja distorceu o
# resultado: em 2005 o mercado brasileiro nao tinha 150 acoes liquidas, entao o top 150
# descia ate papel com R$1.273 de volume diario, cuja oscilacao domina a media.
LIQUIDEZ_MINIMA = 1_000_000.0
# Retorno so entra se o pregao anterior do papel for recente. Sem isso, uma acao que
# ficou 30 dias sem negociar injeta o retorno de 30 dias dentro de um retorno de 1 dia.
DIAS_MAXIMOS_SEM_NEGOCIAR = 5
# Retorno diario do mercado brasileiro acima disso nao existe. Serve para flagrar erro na
# propria referencia (ver comentario em relatorio()), nao para filtrar o nosso dado.
LIMITE_PLAUSIVEL_MERCADO = 0.10
# ... e so e considerada erro da referencia se ela tambem DISCORDAR da nossa carteira
# alem deste limite. Crise real move os dois juntos; erro de dado move so um.
DISCORDANCIA_MAXIMA = 0.08


def _carteira_mensal() -> pd.DataFrame:
    """Top N por volume financeiro mediano de 12 meses, recomposto todo mes.

    Seleciona com informacao ATE o mes anterior, nunca do mes corrente: senao a propria
    carteira de teste teria look-ahead, e o resultado nao serviria para auditar nada.
    """
    with warehouse.connect(read_only=True) as con:
        return con.execute(f"""
            WITH base AS (
                SELECT ticker, data,
                       -- retorno CRU: sem ajuste nenhum, direto do preco nominal. E o
                       -- contrafactual do teste -- se ajustar nao aproximar a serie da
                       -- referencia externa, o ajuste nao esta fazendo nada.
                       fechamento / lag(fechamento) OVER (PARTITION BY ticker ORDER BY data)
                         - 1 AS retorno_cru,
                       retorno_qtd, retorno_total,
                       fechamento,
                       median(volume) OVER (
                           PARTITION BY ticker ORDER BY data
                           ROWS BETWEEN {JANELA_LIQUIDEZ} PRECEDING AND 1 PRECEDING
                       ) AS liquidez_passada,
                       lag(fechamento) OVER (PARTITION BY ticker ORDER BY data) AS fech_ant,
                       lag(data)       OVER (PARTITION BY ticker ORDER BY data) AS data_ant,
                       -- Valor de mercado do pregao ANTERIOR: o peso tem que ser o de
                       -- antes do retorno que ele vai ponderar, senao a carteira se
                       -- pondera pelo proprio resultado do dia.
                       lag(valor_mercado_classe) OVER (PARTITION BY ticker ORDER BY data)
                         AS peso_valor
                FROM acoes_diario
                WHERE classe IN ('on','pn')
            ),
            elegivel AS (
                SELECT *, date_trunc('month', data) AS mes
                FROM base
                WHERE liquidez_passada >= {LIQUIDEZ_MINIMA}
                  AND fech_ant >= {PRECO_MINIMO}
                  AND retorno_qtd IS NOT NULL
                  AND datediff('day', data_ant, data) <= {DIAS_MAXIMOS_SEM_NEGOCIAR}
            ),
            ranqueado AS (
                SELECT *, row_number() OVER (
                    PARTITION BY mes, data ORDER BY liquidez_passada DESC
                ) AS posicao
                FROM elegivel
            )
            SELECT data, ticker, retorno_cru, retorno_qtd, retorno_total, peso_valor
            FROM ranqueado
            WHERE posicao <= {TOP_LIQUIDEZ}
        """).df()


def _referencia() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        ref = con.execute("""
            SELECT data, rm_minus_rf + risk_free AS retorno_mercado
            FROM nefin_fatores
            WHERE rm_minus_rf IS NOT NULL
        """).df()
    ref["data"] = pd.to_datetime(ref["data"])
    return ref


def relatorio() -> None:
    pd.set_option("display.width", 200)
    carteira = _carteira_mensal()
    carteira["data"] = pd.to_datetime(carteira["data"])

    # DUAS PONDERACOES, e a segunda foi acrescentada em 14/09/2026 por um motivo
    # especifico. O comentario que estava aqui dizia que sem quantidade de acoes nao dava
    # para ponderar por valor -- e isso envelheceu: a ingestao do capital social da CVM
    # trouxe `valor_mercado_classe` para a base diaria.
    #
    # Por que importa. Em 11/09/2026 o desvio do ACUMULADO contra o NEFIN se afastou
    # depois da correcao dos grupamentos, e ficou registrado como "ponto a vigiar" porque
    # as duas series nao eram comparaveis em NIVEL: peso igual contra um fator ponderado
    # por valor. Isso nao e detalhe -- peso igual carrega a cauda pequena inteira, que e
    # exatamente onde vive o retorno que a correcao removeu. Sem a versao ponderada nao
    # da para dizer se o desvio e defeito nosso ou artefato da comparacao.
    #
    # A equiponderada CONTINUA sendo a serie do contraste cru-vs-ajustado, que nao depende
    # de ponderacao. A ponderada existe para o nivel.
    colunas = ["retorno_cru", "retorno_qtd", "retorno_total"]
    diario = carteira.groupby("data")[colunas].mean()
    c = carteira.dropna(subset=["peso_valor"])
    c = c[c["peso_valor"] > 0]
    ponderada = (c.groupby("data")
                  .apply(lambda g: pd.Series(
                      {f"{col}_vw": float(np.average(g[col], weights=g["peso_valor"]))
                       for col in colunas}), include_groups=False))
    diario = diario.join(ponderada)
    n_ativos = carteira.groupby("data").size().rename("n")

    ref = _referencia().set_index("data")["retorno_mercado"]
    j = diario.join(ref, how="inner").join(n_ativos).dropna(subset=["retorno_mercado"])

    # A REFERENCIA TAMBEM PODE ESTAR ERRADA, e neste caso esta.
    # Achado real: em 12/06/2025 o fator SMB do NEFIN marca +23,37%; em 13/06 o mercado
    # marca +13,47% e em 16/06 marca -10,92%. A mediana de 331 acoes nossas nesses dias e
    # -0,50% e +1,13%. A bolsa brasileira nao fez isso. O erro esta na serie do NEFIN.
    # Auditoria so vale se olhar para os dois lados: sem esta marcacao, um defeito da
    # referencia entraria no relatorio como defeito nosso.
    # Cuidado que quase custou caro: filtrar so por "|retorno| > 10%" marcava 10 dias, e
    # 8 deles eram outubro de 2008 e marco de 2020 -- dias em que a bolsa ANDOU mesmo mais
    # de 10%. Excluir crise de uma auditoria e jogar fora exatamente a observacao que mais
    # importa para risco. O discriminante certo nao e o tamanho do movimento, e a
    # DISCORDANCIA: em 2008 e 2020 a nossa carteira despenca junto com a referencia; em
    # 13/06/2025 a referencia marca +13,5% enquanto a nossa fica em -1%.
    j["referencia_suspeita"] = (
        (j["retorno_mercado"].abs() > LIMITE_PLAUSIVEL_MERCADO)
        & ((j["retorno_mercado"] - j["retorno_qtd"]).abs() > DISCORDANCIA_MAXIMA)
    )
    suspeitos = j[j["referencia_suspeita"]]
    if not suspeitos.empty:
        print(f"\nAVISO: {len(suspeitos)} pregao(oes) com o fator do NEFIN fora do plausivel "
              f"(|retorno| > {100*LIMITE_PLAUSIVEL_MERCADO:.0f}%): "
              f"{', '.join(d.strftime('%Y-%m-%d') for d in suspeitos.index)}")
        print("       excluidos das metricas abaixo; problema da referencia, nao do nosso dado.")
    j = j[~j["referencia_suspeita"]]

    print("=" * 74)
    print("AUDITORIA DAS SERIES DE PRECO CONTRA O FATOR DE MERCADO DO NEFIN")
    print("=" * 74)
    print(f"periodo: {j.index.min():%Y-%m-%d} a {j.index.max():%Y-%m-%d}   "
          f"pregoes: {len(j):,}   ativos/dia (mediana): {j['n'].median():.0f}")

    linhas = []
    for col, rotulo in (("retorno_cru", "cru (sem ajuste)"),
                        ("retorno_qtd", "ajustado por quantidade"),
                        ("retorno_total", "retorno total"),
                        ("retorno_cru_vw", "cru, ponderado por valor"),
                        ("retorno_qtd_vw", "ajustado, ponderado por valor"),
                        ("retorno_total_vw", "retorno total, ponderado por valor")):
        if col not in j.columns:
            continue
        s = j[col].dropna()
        mercado = j["retorno_mercado"].reindex(s.index)
        corr = s.corr(mercado)
        dif = s - mercado
        # Retorno acumulado do periodo, comparavel com o do fator.
        acum = float(np.expm1(np.log1p(s).sum()))
        linhas.append({
            "serie": rotulo,
            "correlacao": round(corr, 4),
            "erro_abs_medio_bps": round(1e4 * dif.abs().mean(), 1),
            "pregoes": len(s),
            "desvio_do_acum_pp": round(100 * (acum - float(np.expm1(np.log1p(mercado).sum()))), 1),
        })
    ref_acum = float(np.expm1(np.log1p(j["retorno_mercado"]).sum()))
    print(f"\nretorno acumulado do fator NEFIN no periodo: {100*ref_acum:,.0f}%\n")
    print(pd.DataFrame(linhas).to_string(index=False))

    ganho = (pd.DataFrame(linhas).set_index("serie").loc["ajustado por quantidade", "correlacao"]
             - pd.DataFrame(linhas).set_index("serie").loc["cru (sem ajuste)", "correlacao"])
    print(f"\nganho de correlacao do ajuste: {ganho:+.4f}")
    if ganho <= 0.0005:
        print("ALERTA: o ajuste nao melhorou nada. Ou nao esta sendo aplicado, ou o\n"
              "        universo liquido quase nao tem evento -- investigar antes de confiar.")

    print("\n" + "=" * 74)
    print("OS PIORES DIAS -- onde a serie crua mais se afasta do mercado")
    print("=" * 74)
    j = j.copy()
    j["erro_cru"] = (j["retorno_cru"] - j["retorno_mercado"]).abs()
    j["erro_ajustado"] = (j["retorno_qtd"] - j["retorno_mercado"]).abs()
    piores = j.nlargest(10, "erro_cru")[
        ["retorno_cru", "retorno_qtd", "retorno_mercado", "erro_cru", "erro_ajustado"]]
    print((100 * piores).round(2).to_string())
    print("\nSe o ajuste funciona, erro_ajustado tem que ser bem menor que erro_cru nestas linhas.")


if __name__ == "__main__":
    relatorio()
