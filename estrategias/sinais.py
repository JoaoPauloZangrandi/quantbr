"""As tres familias que o Joao considera o minimo de um hedge fund.

Cada sinal e uma funcao pura sobre `emissor_mensal` que devolve (cnpj, ano_mes, sinal),
com a convencao de que MAIOR e melhor. Quem defasa o retorno e o motor, nunca o sinal --
defasagem feita em dois lugares e defasagem feita em nenhum.

  momento     continuacao. O que subiu nos ultimos 12 meses tende a continuar subindo.
  reversao    correcao. O que caiu demais no ultimo mes tende a voltar.
  armagedom   sobrevivencia. O que fazer quando tudo cai junto.

As tres nao sao independentes: momento e reversao sao o mesmo fenomeno em horizontes
diferentes, e e por isso que o momento PULA o mes mais recente -- para nao apostar contra
si mesmo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse


def _painel(colunas: str = "cnpj, ano_mes, retorno_total") -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        return con.execute(f"""
            SELECT {colunas} FROM emissor_mensal ORDER BY cnpj, ano_mes
        """).df()


def momento(formacao: int = 12, pulo: int = 1) -> pd.DataFrame:
    """Momento 12-1: retorno acumulado de 12 meses, PULANDO o mes mais recente.

    O pulo nao e detalhe de implementacao, e a diferenca entre momento e reversao. O mes
    imediatamente anterior carrega reversao de curto prazo -- microestrutura, pressao de
    liquidez, bid-ask bounce -- que anda no sentido OPOSTO ao momento. Jegadeesh e Titman
    (1993) documentam a continuacao de 3 a 12 meses; a literatura de reversao documenta o
    contrario em 1 mes. Incluir o ultimo mes mistura os dois e enfraquece os dois.

    O bid-ask bounce merece nota porque a nossa base agora deixa medir: o preco de
    fechamento alterna entre bid e ask por acaso, e isso cria reversao artificial em papel
    de spread largo -- justamente a cauda em que o spread mediano passa de 3%.
    """
    d = _painel()
    # Acumulado de `formacao` meses terminando `pulo` meses atras. Em log para somar em
    # vez de multiplicar; o clip evita -inf em papel que perdeu tudo num mes.
    d["log_ret"] = np.log1p(d["retorno_total"].clip(lower=-0.99))
    acum = (d.groupby("cnpj")["log_ret"]
              .rolling(formacao, min_periods=formacao).sum()
              .reset_index(level=0, drop=True))
    d["sinal"] = np.expm1(acum.groupby(d["cnpj"]).shift(pulo))
    return d[["cnpj", "ano_mes", "sinal"]]


def reversao(janela: int = 1) -> pd.DataFrame:
    """Reversao de curto prazo: o que caiu mais no ultimo mes.

    Sinal invertido de proposito -- maior sinal = mais caiu = mais se espera que volte.

    ADVERTENCIA QUE A NOSSA PROPRIA BASE IMPOE. Reversao de 1 mes e a estrategia de giro
    mais alto que existe: 12 rebalanceamentos por ano, por construcao. Medido aqui, isso
    custa 16,7% ao ano na faixa de R$100 mi a 1 bi e 54% ao ano abaixo de R$100 mi. E
    pior: boa parte da reversao medida em papel iliquido e bid-ask bounce, nao retorno --
    o fechamento alterna entre a ponta de compra e a de venda, e isso PARECE reversao sem
    que ninguem consiga captura-la. Por isso o motor cobra o spread do proprio papel.
    """
    d = _painel()
    if janela == 1:
        d["sinal"] = -d["retorno_total"]
    else:
        d["log_ret"] = np.log1p(d["retorno_total"].clip(lower=-0.99))
        acum = (d.groupby("cnpj")["log_ret"]
                  .rolling(janela, min_periods=janela).sum()
                  .reset_index(level=0, drop=True))
        d["sinal"] = -np.expm1(acum)
    return d[["cnpj", "ano_mes", "sinal"]]


def defensivo_armagedom(janela: int = 12) -> pd.DataFrame:
    """Armagedom: preferir quem cai menos quando o mercado cai.

    A pergunta desta familia nao e "o que sobe mais", e "o que segura a carteira quando
    tudo cai junto". Duas caracteristicas respondem a isso, e as duas estao na base:

      1. **beta de queda** -- quanto o papel cai nos meses em que o mercado cai. Nao e o
         beta cheio: numa crise a correlacao sobe e o que importa e o comportamento na
         cauda, nao na media.
      2. **volatilidade propria** -- papel calmo tende a continuar calmo, e o efeito
         low-volatility e um dos poucos que sobrevive fora dos EUA.

    Sinal = menor beta de queda, com desempate por menor volatilidade. Maior sinal =
    mais defensivo.

    O QUE ESTA FAMILIA NAO E. Nao e hedge. Uma carteira defensiva cai menos, mas cai --
    e num armagedom de verdade a correlacao vai a um e a protecao encolhe justamente
    quando e mais necessaria. Protecao de cauda de verdade exige opcao ou posicao vendida,
    e a base ainda nao tem nem uma nem outra (opcao esta fora do escopo; aluguel por papel
    exige o arquivo BTB da B3). Isto e o melhor que se faz SO COM ACAO A VISTA, e a
    limitacao fica escrita para ninguem confundir com seguro.
    """
    d = _painel()
    mercado = (d.groupby("ano_mes")["retorno_total"].mean()
                 .rename("mercado").reset_index())
    d = d.merge(mercado, on="ano_mes", how="left")
    d = d.sort_values(["cnpj", "ano_mes"])

    # Beta de queda: covariancia com o mercado apenas nos meses em que o mercado caiu.
    d["queda"] = d["mercado"] < 0
    def _beta_queda(g: pd.DataFrame) -> pd.Series:
        saida = []
        for i in range(len(g)):
            jan = g.iloc[max(0, i - janela + 1): i + 1]
            jan = jan[jan["queda"]]
            if len(jan) < 4 or jan["mercado"].std() == 0:
                saida.append(np.nan)
                continue
            saida.append(float(np.cov(jan["retorno_total"], jan["mercado"])[0, 1]
                               / jan["mercado"].var()))
        return pd.Series(saida, index=g.index)

    d["beta_queda"] = d.groupby("cnpj", group_keys=False).apply(_beta_queda)
    d["vol"] = (d.groupby("cnpj")["retorno_total"]
                  .rolling(janela, min_periods=6).std()
                  .reset_index(level=0, drop=True))
    # Menor beta de queda e melhor; volatilidade entra como desempate suave.
    d["sinal"] = -(d["beta_queda"].rank(pct=True) + 0.5 * d["vol"].rank(pct=True))
    return d[["cnpj", "ano_mes", "sinal"]]
