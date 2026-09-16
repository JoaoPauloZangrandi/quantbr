"""Por que PULO 0 bate PULO 1 no momento -- a pendencia nº4 de 14/09/2026.

A PERGUNTA

Na grade de 24 variacoes do momento, as versoes que NAO pulam o mes mais recente batem as
que pulam em 9 dos 12 pares (formacao x numero de papeis), e no ponto da literatura a
diferenca e grande: 12-1 com 20 papeis da Sharpe 0,157; 12-0 da 0,296.

Isso contraria o motivo declarado do pulo. Jegadeesh e Titman (1993) pulam o mes recente
porque ele carrega REVERSAO de curto prazo -- microestrutura, pressao de liquidez,
bid-ask bounce -- que andaria contra o momento. Se pular piora, a premissa nao vale aqui.

A HIPOTESE, E ELA JA ESTAVA MEDIDA NO PROPRIO ALICERCE

A familia "reversao 1 mes" perde 24 pontos percentuais para o CDI e tem Sharpe -0,63. Ela
compra quem MAIS CAIU no ultimo mes. Se comprar quem caiu perde feio, entao no mes seguinte
quem caiu continua caindo -- ou seja, o horizonte de 1 mes tem CONTINUACAO, nao reversao.
E a mesma coisa que o pulo 0 diz, medida de outro jeito. Duas leituras do mesmo fato.

O QUE ESTE MODULO MEDE

O spread transversal do sort de 1 mes: quintil de maior retorno no mes t menos quintil de
menor retorno, realizado em t+1. Positivo = continuacao; negativo = reversao. Junto vem o
que o protocolo de leitura de resultado exige (ver reference_quant_akhaldoun em memoria):

  - erro padrao e t, com Newey-West, porque a serie mensal tem autocorrelacao;
  - quebra por regime (metade e metade da amostra) -- padrao que so existe numa metade
    nao e padrao;
  - quebra por liquidez -- se o efeito mora so no papel ilíquido, e microestrutura, nao
    retorno capturavel;
  - o mesmo spread medido sobre o RETORNO DO PONTO MEDIO (bid-ask bounce removido), que e
    a unica forma de separar economia de artefato com o dado que temos.

    python -m estrategias.horizonte_curto
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse
from estrategias import motor

# O piso de liquidez sai do motor, nao de uma copia local: duas definicoes do mesmo
# universo divergem em silencio no dia em que uma das duas muda -- e uma delas mudou, de
# R$500 mil para R$50 mil, em 15/09/2026.
LIQUIDEZ_MINIMA = motor.Parametros().liquidez_minima
MES_INICIAL = "2010-01"
N_QUINTIS = 5


def painel() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        d = con.execute(f"""
            SELECT cnpj, ano_mes, retorno_total, retorno_mid, volume_mediano,
                   valor_mercado_empresa, spread_mediano, custo_roundtrip
            FROM emissor_mensal
            WHERE ano_mes >= '{MES_INICIAL}'
            ORDER BY cnpj, ano_mes
        """).df()
    g = d.groupby("cnpj")
    # O sinal e o retorno do mes t; o que ele tem que explicar e o retorno de t+1.
    for col in ("retorno_total", "retorno_mid"):
        d[f"{col}_prox"] = g[col].shift(-1)
    d["liquidez_prox"] = g["volume_mediano"].shift(-1)
    return d


def _newey_west_t(x: pd.Series, defasagens: int = 6) -> float:
    """t com erro padrao robusto a autocorrelacao. Serie mensal de estrategia tem."""
    x = x.dropna()
    n = len(x)
    if n < 12:
        return np.nan
    media = x.mean()
    e = (x - media).values
    var = float((e @ e) / n)
    for k in range(1, min(defasagens, n - 1) + 1):
        c = float(e[k:] @ e[:-k] / n)
        var += 2 * (1 - k / (defasagens + 1)) * c
    if var <= 0:
        return np.nan
    return media / np.sqrt(var / n)


def spread(d: pd.DataFrame, coluna_sinal: str = "retorno_total",
           coluna_realizado: str = "retorno_total_prox") -> pd.Series:
    """Serie mensal do spread quintil-alto menos quintil-baixo, um mes a frente."""
    d = d.dropna(subset=[coluna_sinal, coluna_realizado]).copy()
    d = d[d["volume_mediano"] >= LIQUIDEZ_MINIMA]
    # A carteira tem que caber: so entra quem continua negociavel no mes em que rende.
    d = d[d["liquidez_prox"].fillna(0) >= LIQUIDEZ_MINIMA]
    saida = {}
    for mes, g in d.groupby("ano_mes"):
        if len(g) < 2 * N_QUINTIS:
            continue
        q = pd.qcut(g[coluna_sinal].rank(method="first"), N_QUINTIS, labels=False)
        alto = g.loc[q == N_QUINTIS - 1, coluna_realizado].mean()
        baixo = g.loc[q == 0, coluna_realizado].mean()
        saida[mes] = alto - baixo
    return pd.Series(saida).sort_index()


def taxa_de_aluguel() -> pd.Series:
    """Taxa media de aluguel do mercado, por mes, em fracao ao ano. Fonte: NEFIN.

    E AGREGADA, e isso e um limite que muda a conclusao, nao um detalhe. A perna vendida
    de um sort de perdedores nao aluga o papel medio do mercado: aluga justamente o que
    caiu, que e onde o aluguel escasseia e encarece. A taxa por papel exige o arquivo BTB
    diario da B3, que a base ainda nao tem -- entao o numero daqui e um PISO do custo.
    """
    with warehouse.connect(read_only=True) as con:
        if not warehouse.table_exists(con, "nefin_loan_fee"):
            return pd.Series(dtype=float)
        d = con.execute("""
            SELECT strftime(data, '%Y-%m') AS ano_mes,
                   median(average_loan_fee) / 100.0 AS taxa
            FROM nefin_loan_fee GROUP BY 1 ORDER BY 1
        """).df()
    return d.set_index("ano_mes")["taxa"]


def custo_mensal(d: pd.DataFrame, coluna_sinal: str = "retorno_total") -> pd.Series:
    """Custo de rodar o spread por um mes: ida e volta das DUAS pernas.

    O sort de 1 mes se refaz todo mes por construcao, entao o giro e de 100% ao mes em
    cada perna. Cada papel paga o `custo_roundtrip` dele -- spread medido daquele papel
    naquele mes mais tarifa --, nao uma media do universo: o quintil dos perdedores e mais
    caro de negociar que o universo, e usar a mediana esconderia exatamente isso.
    """
    d = d.dropna(subset=[coluna_sinal, "custo_roundtrip"]).copy()
    d = d[(d["volume_mediano"] >= LIQUIDEZ_MINIMA)
          & (d["liquidez_prox"].fillna(0) >= LIQUIDEZ_MINIMA)]
    saida = {}
    for mes, g in d.groupby("ano_mes"):
        if len(g) < 2 * N_QUINTIS:
            continue
        q = pd.qcut(g[coluna_sinal].rank(method="first"), N_QUINTIS, labels=False)
        alto = g.loc[q == N_QUINTIS - 1, "custo_roundtrip"].mean()
        baixo = g.loc[q == 0, "custo_roundtrip"].mean()
        saida[mes] = alto + baixo
    return pd.Series(saida).sort_index()


def _linha(nome: str, s: pd.Series) -> str:
    if s.dropna().empty:
        return f"{nome:<34} (sem meses)"
    anual = s.mean() * 12
    return (f"{nome:<34} {anual:+7.1%} a.a. {s.mean():+7.2%}/mes "
            f" t={_newey_west_t(s):5.2f}  meses={s.notna().sum():>4}"
            f"  acerto={(s > 0).mean():5.1%}")


def relatorio() -> str:
    d = painel()
    linhas = ["SPREAD DO SORT DE 1 MES (quintil alto - quintil baixo, realizado em t+1)",
              "positivo = CONTINUACAO (o que subiu continua subindo); negativo = reversao",
              ""]
    s = spread(d)
    linhas.append(_linha("tudo, retorno total", s))
    linhas.append(_linha("tudo, retorno do ponto medio",
                         spread(d, "retorno_mid", "retorno_mid_prox")))
    linhas.append("")

    meio = s.index[len(s) // 2]
    linhas.append(_linha(f"primeira metade (ate {meio})", s[s.index <= meio]))
    linhas.append(_linha(f"segunda metade (apos {meio})", s[s.index > meio]))
    linhas.append("")

    # Liquidez: se o efeito so existe no papel fino, e microestrutura.
    # Os tercos sao formados DENTRO do universo negociavel (acima do piso nos dois meses),
    # nao dentro da base inteira. Sem isso o terco de baixo fica vazio depois do filtro --
    # seriam tercos de um universo em que a estrategia nem pode comprar.
    d = d.dropna(subset=["volume_mediano"]).copy()
    d = d[(d["volume_mediano"] >= LIQUIDEZ_MINIMA)
          & (d["liquidez_prox"].fillna(0) >= LIQUIDEZ_MINIMA)]
    corte = d.groupby("ano_mes")["volume_mediano"].transform(
        lambda x: x.rank(pct=True))
    for nome, faixa in (("terco mais liquido", corte > 2 / 3),
                        ("terco do meio", (corte > 1 / 3) & (corte <= 2 / 3)),
                        ("terco menos liquido", corte <= 1 / 3)):
        linhas.append(_linha(nome, spread(d[faixa])))
    linhas.append("")

    # O CUSTO E QUE DECIDE SE ISSO VIRA ESTRATEGIA, e ate aqui so o bruto foi medido.
    linhas.append("DO BRUTO AO LIQUIDO (long-short, giro de 100% ao mes nas duas pernas)")
    custo = custo_mensal(painel())
    aluguel = taxa_de_aluguel()
    comum = s.index.intersection(custo.index)
    bruto = s.reindex(comum)
    c = custo.reindex(comum)
    # Aluguel incide so na perna vendida, e so nos meses em que a serie do NEFIN existe.
    a = (aluguel.reindex(comum) / 12).fillna(0.0)
    linhas.append(_linha("  bruto", bruto))
    linhas.append(_linha("  menos custo de negociacao", bruto - c))
    linhas.append(_linha("  menos custo e aluguel", bruto - c - a))
    linhas.append(f"  ida e volta das duas pernas: {c.mean():.2%}/mes "
                  f"({12 * c.mean():.1%} a.a.)")
    if not aluguel.empty:
        cobertos = int(aluguel.reindex(comum).notna().sum())
        linhas.append(f"  aluguel medio do mercado (NEFIN): {aluguel.mean():.2%} a.a., "
                      f"em {cobertos} dos {len(comum)} meses -- taxa AGREGADA, "
                      f"e portanto um PISO do custo da perna vendida")
    return "\n".join(linhas)


if __name__ == "__main__":
    print(relatorio())
