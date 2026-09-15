"""O motor de backtest. Mede estrategia; nao propoe nenhuma.

POR QUE ESCREVER O PROPRIO MOTOR EM VEZ DE USAR BIBLIOTECA. Porque as decisoes que
determinam o resultado sao justamente as que uma biblioteca esconde: quando o sinal fica
disponivel, o que se paga para entrar e sair, quanto cabe, e o que acontece com o papel que
deixa de existir. Errar qualquer uma delas produz um resultado bonito e falso, e a
biblioteca nao avisa.

AS QUATRO REGRAS DESTE MOTOR

1. **O sinal do mes t decide a carteira que rende em t+1.** Nunca o retorno do proprio mes.
   E a regra que separa backtest de ilusao, e ela e implementada por um `shift`, nao por
   promessa.

2. **Custo e cobrado sobre o giro, com o spread do papel.** Nao um numero redondo para
   todos: o custo de ida e volta vem de `emissor_mensal.custo_roundtrip`, que sai do spread
   medido daquele papel naquele mes mais a tarifa da B3. Medido na base, ele vai de 0,20%
   em papel grande a 4,50% em papel pequeno -- usar uma media unica esconde exatamente a
   diferenca que decide se a estrategia de small cap vive.

3. **Capacidade e reportada, nao ignorada.** Toda rodada devolve quanto capital caberia na
   carteira. Estrategia que rende 30% ao ano com capacidade de R$50 mil nao e estrategia, e
   curiosidade.

4. **Toda rodada e gravada no ledger de trials.** Inclusive as que morreram. Sem o
   denominador de tentativas nao ha como corrigir por teste multiplo depois, e uma casa de
   research que so guarda o que deu certo esta construindo um viesde selecao proprio.

O QUE ESTE MOTOR NAO FAZ

Nao decide universo por conta propria e nao filtra em silencio: o filtro de liquidez e
parametro, entra no resultado e vai para o ledger. Nao usa alavancagem. Nao modela impacto
de mercado alem do spread -- impacto depende do tamanho da ordem, e isso e decisao de quem
for operar, nao do motor.
"""
from __future__ import annotations

import dataclasses as dc
import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

import config
import warehouse

MESES_NO_ANO = 12


@dc.dataclass(frozen=True)
class Parametros:
    """Tudo que muda o resultado fica aqui, e vai inteiro para o ledger."""
    n_papeis: int = 20
    # Filtro de negociabilidade: volume financeiro mediano diario minimo para o papel
    # poder ENTRAR na carteira. O default nao e neutro, e nunca foi.
    #
    # DECISAO DO JOAO EM 15/09/2026: R$ 50 mil, no lugar dos R$ 500 mil anteriores. E o
    # universo mais largo que este motor ja rodou (192 empresas elegiveis por mes, contra
    # 146), e o preco esta medido e e alto -- ver `estrategias/capacidade.py` e a entrada
    # de 15/09 no DIARIO.md:
    #
    #   piso      elegiveis/mes   benchmark   momento 12-1   custo do momento   capacidade
    #   R$  50k       192           -0,12        -0,04            5,0% a.a.      R$ 0,8 mi
    #   R$ 500k       146           -0,03        +0,16            2,1% a.a.      R$ 6,9 mi
    #   R$  50 mi      42           -0,17        +0,21            0,6% a.a.      R$ 536 mi
    #
    # Ou seja: descer o piso NAO e neutro, e a direcao contraria a que a curva aponta. A
    # cauda abaixo de R$500 mil/dia cobra spread de ida e volta de ate 4,50%, e a esse
    # custo o momento volta a perder do CDI. Fica registrado que a escolha e deliberada e
    # que o numero que ela produz e a barra nova.
    liquidez_minima: float = 50_000.0
    # Retorno usado. 'retorno_total' inclui provento; 'retorno_qtd' so ajusta quantidade.
    # A escolha muda o resultado e por isso e explicita -- regra do projeto: nao existe
    # "o preco".
    coluna_retorno: str = "retorno_total"
    mes_inicial: str = "2010-01"   # antes disso nao ha valor de mercado nem balanco
    mes_final: str = "2026-09"
    long_short: bool = False       # False = so comprado; True = compra topo, vende fundo
    # O que se assume que rendeu a posicao cujo mes seguinte nao existe no painel e que
    # tambem nao tem retorno de delisting -- papel que simplesmente parou de negociar.
    # 0.0 e "dinheiro preso, sem ganho nem perda"; -1.0 e "perda total". A escolha muda o
    # resultado, entao e parametro declarado e vai para o ledger, nao constante escondida.
    retorno_posicao_presa: float = 0.0


def _painel(par: Parametros) -> pd.DataFrame:
    """O painel INTEIRO do periodo. Sem filtro de liquidez -- de proposito.

    O filtro de liquidez decide quem pode ser COMPRADO, e por isso e aplicado na formacao
    da carteira (`_elegiveis`). Aplica-lo aqui apagava junto o CAMINHO de uma posicao ja
    comprada: o papel que seca no mes seguinte -- cai abaixo de R$500 mil/dia -- sumia do
    painel e a posicao evaporava sem retorno nenhum. A carteira ficava, por construcao,
    com a parte liquida do que ela mesma comprou.

    E a outra metade do achado A do Codex (11/09/2026). Quem compra no limite da liquidez
    sabe que ela pode secar; o motor tem que MEDIR isso, nao apagar.
    """
    with warehouse.connect(read_only=True) as con:
        return con.execute(f"""
            SELECT cnpj, ano_mes, ticker, nome,
                   {par.coluna_retorno} AS retorno,
                   volume_mediano, custo_roundtrip, capacidade_dia,
                   valor_mercado_empresa, pregoes_no_mes, negociou_no_fim_do_mes,
                   motivo_saida, retorno_delisting
            FROM emissor_mensal
            WHERE ano_mes BETWEEN '{par.mes_inicial}' AND '{par.mes_final}'
            ORDER BY cnpj, ano_mes
        """).df()


def _elegiveis(px: pd.DataFrame, par: Parametros) -> pd.DataFrame:
    """Quem pode ENTRAR na carteira neste mes. Nao confundir com quem pode ser MEDIDO.

    Duas condicoes, e a segunda foi acrescentada em 14/09/2026:

      1. negociabilidade -- volume mediano diario acima do piso;
      2. estar A VENDA no instante da formacao. A carteira se forma no fechamento do
         ultimo pregao do mes; papel que ja tinha parado de negociar antes disso nao da
         para comprar naquele dia, por mais alto que esteja o sinal.

    A segunda saiu de olhar as 78 "posicoes presas" do achado E uma a uma: 53 delas (68%)
    tinham menos de 15 pregoes no mes da formacao, contra 1,3% do universo, e 66 eram
    empresa saindo da bolsa -- AMBEV, Souza Cruz, CETIP, Rumo, Smiles, TAM. Nao eram
    posicoes que ficaram presas depois de compradas: eram compras impossiveis. Isso NAO e
    informacao do futuro -- e o que qualquer um veria na tela no dia da formacao.

    Custa 0,58% das linhas elegiveis (229 de 39.152).
    """
    pode = px["volume_mediano"] >= par.liquidez_minima
    if "negociou_no_fim_do_mes" in px.columns:
        pode &= px["negociou_no_fim_do_mes"].fillna(True).astype(bool)
    return px[pode]


def _mes_seguinte(ano_mes) -> pd.Index:
    """'2020-01' -> '2020-02'. Mes de CALENDARIO, nao proximo registro do painel."""
    idx = pd.Index(ano_mes)
    if len(idx) == 0:
        return idx
    return pd.Index((pd.PeriodIndex(idx, freq="M") + 1).strftime("%Y-%m"))


def _casar_retorno_futuro(alvo: pd.DataFrame, painel: pd.DataFrame,
                          retorno_presa: float = 0.0) -> pd.DataFrame:
    """Cola em cada linha o retorno do MES DE CALENDARIO seguinte, e o rotula.

    Nao usa `shift(-1)`. O shift anda para o proximo REGISTRO, e registro nao e mes: se o
    papel some do painel em fevereiro -- porque nao negociou, porque caiu do filtro de
    liquidez, ou porque o sinal nao existe naquele mes -- o shift entrega marco e chama de
    "mes seguinte". O sinal de janeiro passa a ser julgado por um retorno que ele nao tinha
    como prever, e dois meses de mercado entram no lugar de um.

    Achado pelo Codex em 11/09/2026 com painel sintetico: 2% viravam 30% ao remover um
    unico mes do meio. A fonte do retorno e o painel INTEIRO, nao o painel ja cruzado com
    o sinal -- senao a propria ausencia de sinal abre a lacuna.

    Quem nao tem mes seguinte no painel fica com o retorno de delisting, se houver. Se nao
    houver, a linha CONTINUA, com `posicao_presa = True` e o retorno declarado em
    `par.retorno_posicao_presa`.

    POR QUE ELA NAO PODE SER DESCARTADA (achado E do Codex, 11/09/2026). Descartar antes
    de rankear faz a SELECAO depender de o papel existir no futuro: o ativo de maior sinal
    que parou de negociar sumia da cross-section e o 21o colocado herdava a vaga. Isso nao
    e conservadorismo, e look-ahead com sinal invertido -- o motor so escolhia entre os que
    sobreviveram. A resposta honesta nao e apagar a posicao, e carrega-la com uma hipotese
    escrita sobre o que ela rendeu.

    O unico descarte que fica e o do mes que AINDA NAO ACONTECEU: formacao cujo mes de
    realizacao passa do fim do painel nao e posicao presa, e mes que nao existe.
    """
    d = alvo.copy()
    d["mes_realizacao"] = _mes_seguinte(d["ano_mes"])
    fonte = (painel[["cnpj", "ano_mes", "retorno"]]
             .rename(columns={"ano_mes": "mes_realizacao", "retorno": "retorno_futuro"}))
    d = d.merge(fonte, on=["cnpj", "mes_realizacao"], how="left")
    # Papel que sai da base leva o retorno de delisting, em vez de sumir.
    saiu = d["retorno_futuro"].isna() & d["retorno_delisting"].notna()
    d.loc[saiu, "retorno_futuro"] = d.loc[saiu, "retorno_delisting"]
    # Mes que nao existe no painel INTEIRO nao e posicao presa, e mes que a base nao tem
    # -- inclusive o mes seguinte ao fim do periodo. Esse sai. Ja o mes que existe para o
    # mercado e falta para ESTE papel e posicao presa, e fica.
    d = d[d["mes_realizacao"].isin(set(painel["ano_mes"]))]
    d["posicao_presa"] = d["retorno_futuro"].isna()
    d["retorno_futuro"] = d["retorno_futuro"].fillna(retorno_presa)
    return d


def _risk_free_mensal() -> pd.Series:
    """CDI acumulado por mes. Sem isto nao existe Sharpe, so razao retorno/vol.

    No Brasil isso nao e preciosismo: com a taxa basica em dois digitos, uma estrategia
    que rende 11% ao ano nao rendeu nada -- rendeu o CDI. Ignorar o risk-free aqui
    inverteria o ranking entre as familias, e foi o que quase aconteceu na primeira
    rodada de 10/09/2026.
    """
    with warehouse.connect(read_only=True) as con:
        d = con.execute("""
            SELECT strftime(data, '%Y-%m') AS ano_mes,
                   exp(sum(ln(fator_dia))) - 1 AS rf
            FROM taxa_livre_risco WHERE serie = 'cdi' AND fator_dia > 0
            GROUP BY 1 ORDER BY 1
        """).df()
    return d.set_index("ano_mes")["rf"]


def _metricas(retornos: pd.Series, rf: pd.Series | None = None) -> dict:
    r = retornos.dropna()
    if len(r) < 12:
        return {"meses": len(r)}
    acum = float((1 + r).prod())
    anos = len(r) / MESES_NO_ANO
    cagr = acum ** (1 / anos) - 1
    vol = float(r.std()) * np.sqrt(MESES_NO_ANO)
    curva = (1 + r).cumprod()
    dd = float((curva / curva.cummax() - 1).min())
    # Sharpe de verdade: EXCESSO sobre o CDI, nao retorno sobre volatilidade.
    if rf is not None:
        excesso = (r - rf.reindex(r.index)).dropna()
        cdi_anual = float((1 + rf.reindex(r.index).dropna()).prod()) ** (
            MESES_NO_ANO / max(len(rf.reindex(r.index).dropna()), 1)) - 1
        sharpe = (float(excesso.mean()) * MESES_NO_ANO
                  / (float(excesso.std()) * np.sqrt(MESES_NO_ANO))) if len(excesso) > 1 else np.nan
    else:
        cdi_anual, sharpe = np.nan, np.nan
    return {
        "meses": len(r),
        "retorno_anual": cagr,
        "cdi_anual": cdi_anual,
        "retorno_sobre_cdi": cagr - cdi_anual,
        "vol_anual": vol,
        "sharpe": sharpe,
        "max_drawdown": dd,
        "meses_positivos": float((r > 0).mean()),
        "pior_mes": float(r.min()),
    }


DIAS_PARA_MONTAR = 5


def _andar_com_o_mercado(alvo: pd.Series, retorno: pd.Series) -> pd.Series:
    """Os pesos que a carteira TEM no fim do mes, depois de o mercado andar com ela.

    Sem isto o rebalanceamento e de graca. O motor calcula o retorno bruto como MEDIA dos
    papeis, o que ja supoe voltar a peso igual todo mes -- mas cobrava custo so de quem
    ENTROU e SAIU da carteira. O papel que dobrou e ficou virava peso maior e era
    reequilibrado sem pagar nada.

    Achado C do Codex (11/09/2026), reproduzido com dois papeis e um deles dobrando: a
    equalizacao exige 16,67% de giro unilateral que nao aparecia em lugar nenhum. A
    diferenca entre 2,25 e 2,50 de riqueza bruta e exatamente a escolha entre rebalancear
    e nao rebalancear -- as duas sao defensaveis, cobrar a primeira de graca nao e.

    Normaliza pelo bruto para funcionar nas duas pernas: numa carteira so comprada o
    divisor e 1 + retorno da carteira, que e a conta certa; numa long-short os pesos somam
    zero e nao existe divisor unico, entao a convencao declarada e manter a exposicao
    bruta constante.
    """
    v = alvo * (1 + retorno.reindex(alvo.index).fillna(0.0))
    bruto_depois = float(v.abs().sum())
    if bruto_depois <= 0:
        return v * 0.0
    return v * (float(alvo.abs().sum()) / bruto_depois)


def _rebalancear(alvo: pd.Series, anterior: pd.Series,
                 custo_papel: pd.Series, custo_padrao: float) -> tuple[float, float]:
    """Giro unilateral e custo do mes, cobrando de CADA papel o spread DELE.

    Duas correcoes na mesma conta:

    - o giro deixa de ser "quantos nomes mudaram" e passa a ser quanto peso mudou de
      fato, incluindo o reequilibrio de quem ficou (achado C);
    - o custo deixa de ser a MEDIANA da carteira e passa a ser o custo de cada ordem
      (achado F). A mediana e justamente o numero que esconde o problema: quem entra e
      sai de uma carteira de small cap e a ponta cara, e a mediana dos 20 papeis
      mantidos nao sabe disso.

    `custo_roundtrip` e ida e volta; cada ordem paga metade -- meio spread mais a tarifa
    do seu lado. Para troca pura de nomes esta conta devolve exatamente o que o motor
    cobrava antes (k/N x custo), o que torna a mudanca uma extensao, nao outra convencao.
    """
    idx = alvo.index.union(anterior.index)
    delta = (alvo.reindex(idx).fillna(0.0) - anterior.reindex(idx).fillna(0.0)).abs()
    c = custo_papel.reindex(idx).astype(float).fillna(custo_padrao)
    return float(delta.sum()) / 2.0, float((delta * c).sum()) / 2.0


def _capacidade(cap_dia: pd.Series, n_posicoes: int) -> tuple[float, float]:
    """(gargalo, soma). O que vale para carteira de peso igual e o GARGALO.

    Achado D do Codex (11/09/2026). Somar a capacidade dos papeis responde "quanto o
    conjunto absorve se eu puder comprar na proporcao da liquidez de cada um" -- que nao e
    a carteira que este motor simula. Em peso igual cada posicao recebe K/N, e K/N tem que
    caber no MENOS liquido: K <= N x min(capacidade_dia) x dias. No exemplo sintetico do
    Codex a soma dava R$50.500 contra R$1.000 do limite real, 50,5x.

    A soma continua sendo devolvida, porque ela e o teto de uma carteira ponderada por
    liquidez -- estrategia que este projeto pode vir a testar. Mas nao e este numero.
    """
    if cap_dia.empty:
        return 0.0, 0.0
    gargalo = float(cap_dia.min()) * n_posicoes * DIAS_PARA_MONTAR
    return gargalo, float(cap_dia.sum()) * DIAS_PARA_MONTAR


def rodar(sinal: pd.DataFrame, par: Parametros | None = None, *,
          nome: str = "sem_nome", registrar: bool = True,
          painel: pd.DataFrame | None = None) -> dict:
    """`sinal` tem (cnpj, ano_mes, sinal). Maior sinal = melhor.

    O retorno usado e o do mes SEGUINTE ao do sinal. Quem chama nao precisa defasar nada,
    e nao deve: defasagem feita fora do motor e onde look-ahead entra sem ser visto.
    """
    par = par or Parametros()
    # `painel` injetado existe para teste: permite rodar o motor sobre dado sintetico sem
    # tocar o warehouse. Em producao fica None e o painel vem da base.
    px = _painel(par) if painel is None else painel.copy()
    if px.empty:
        return {"erro": "painel vazio"}

    # O filtro de liquidez decide quem ENTRA; o painel inteiro segue como fonte do retorno.
    elegivel = _elegiveis(px, par)
    d = elegivel.merge(sinal.dropna(subset=["sinal"]), on=["cnpj", "ano_mes"], how="inner")
    if d.empty:
        return {"erro": "sinal nao casou com o painel"}

    # O retorno do mes SEGUINTE de calendario, casado contra o painel inteiro.
    d = _casar_retorno_futuro(d.sort_values(["cnpj", "ano_mes"]), px,
                              par.retorno_posicao_presa)
    if d.empty:
        return {"erro": "nenhum sinal teve mes seguinte no painel"}

    # Custo de CADA papel em CADA mes, inclusive o do papel que esta saindo da carteira e
    # portanto nao esta na selecao deste mes.
    custos_do_mes = {m: sub.set_index("cnpj")["custo_roundtrip"]
                     for m, sub in px.groupby("ano_mes", sort=False)}

    linhas = []
    pesos_anteriores = pd.Series(dtype=float)   # pesos no FIM do mes passado, ja com drift
    for mes, g in d.groupby("ano_mes", sort=True):
        if len(g) < par.n_papeis * 2:
            continue   # cross-section pequena demais para formar carteira e contraparte
        g = g.sort_values("sinal", ascending=False)
        topo = g.head(par.n_papeis)
        posicoes = topo
        alvo = pd.Series(1.0 / par.n_papeis, index=topo["cnpj"].to_numpy())
        if par.long_short:
            fundo = g.tail(par.n_papeis)
            posicoes = pd.concat([topo, fundo])
            alvo = pd.concat([alvo,
                              pd.Series(-1.0 / par.n_papeis, index=fundo["cnpj"].to_numpy())])
        retorno = posicoes.set_index("cnpj")["retorno_futuro"]
        bruto = float((alvo * retorno.reindex(alvo.index)).sum())

        custo_papel = custos_do_mes.get(mes, pd.Series(dtype=float))
        custo_padrao = float(posicoes["custo_roundtrip"].median())
        giro, custo = _rebalancear(alvo, pesos_anteriores, custo_papel, custo_padrao)
        pesos_anteriores = _andar_com_o_mercado(alvo, retorno)
        gargalo, soma = _capacidade(posicoes["capacidade_dia"], len(alvo))

        linhas.append({
            # O indice e o mes em que o retorno ACONTECEU, nao o da formacao. O CDI e
            # comparado nesse mes; rotular pela formacao descontava CDI de janeiro de um
            # retorno de fevereiro (achado B do Codex, 11/09/2026).
            "ano_mes": topo["mes_realizacao"].iloc[0],
            "mes_formacao": mes,
            "retorno_bruto": bruto,
            "custo": custo,
            "retorno_liquido": bruto - custo,
            "giro": giro,
            "capacidade": gargalo,
            "capacidade_soma": soma,
            "presas": int(posicoes["posicao_presa"].sum()),
            "n": len(alvo),
        })

    if not linhas:
        return {"erro": "nenhum mes formou carteira"}
    serie = pd.DataFrame(linhas).set_index("ano_mes")
    rf = _risk_free_mensal()

    resultado = {
        "nome": nome,
        "parametros": dc.asdict(par),
        "bruto": _metricas(serie["retorno_bruto"], rf),
        "liquido": _metricas(serie["retorno_liquido"], rf),
        "giro_medio": float(serie["giro"].mean()),
        "custo_anual": float(serie["custo"].mean()) * MESES_NO_ANO,
        # `capacidade_mediana` passa a ser o GARGALO (achado D). Linhas do ledger
        # anteriores a 14/09/2026 guardam a SOMA e nao sao comparaveis com estas.
        "capacidade_mediana": float(serie["capacidade"].median()),
        "capacidade_soma_mediana": float(serie["capacidade_soma"].median()),
        "posicoes_presas": int(serie["presas"].sum()),
        "custo_que_quebra": _custo_que_quebra(serie),
    }
    if registrar:
        _gravar_trial(resultado, serie)
    return resultado


def _custo_que_quebra(serie: pd.DataFrame) -> float:
    """Multiplicador de custo que zera o retorno liquido.

    A pergunta do artigo que o Joao mandou guardar: "aumente o custo ate a estrategia
    quebrar e reporte esse limiar junto do Sharpe". Um resultado que morre com 1,3x de
    custo nao e resultado -- e o spread do dia em que voce precisar sair.
    """
    bruto = float((1 + serie["retorno_bruto"]).prod()) - 1
    if serie["custo"].sum() <= 0:
        return np.inf
    for mult in np.arange(1.0, 20.1, 0.1):
        liq = float((1 + serie["retorno_bruto"] - mult * serie["custo"]).prod()) - 1
        if liq <= 0:
            return round(float(mult), 1)
    return np.inf if bruto > 0 else 0.0


def _gravar_trial(resultado: dict, serie: pd.DataFrame) -> None:
    """Ledger de trials. Grava TUDO, inclusive o que morreu.

    Fica em `protocol/trials.duckdb`, separado do warehouse de proposito: apagar ou
    reconstruir a base de mercado nao pode apagar o historico de tentativas -- e o N de
    tentativas e o que permite corrigir por teste multiplo depois.
    """
    import duckdb
    chave = hashlib.sha256(
        json.dumps({"nome": resultado["nome"], "par": resultado["parametros"]},
                   sort_keys=True).encode()).hexdigest()[:16]
    linha = pd.DataFrame([{
        "trial_id": chave,
        "rodado_em": dt.datetime.now(),
        "nome": resultado["nome"],
        "parametros": json.dumps(resultado["parametros"], sort_keys=True),
        "meses": resultado["liquido"].get("meses"),
        "retorno_anual_bruto": resultado["bruto"].get("retorno_anual"),
        "retorno_anual_liquido": resultado["liquido"].get("retorno_anual"),
        "sharpe_liquido": resultado["liquido"].get("sharpe"),
        "retorno_sobre_cdi": resultado["liquido"].get("retorno_sobre_cdi"),
        "max_drawdown": resultado["liquido"].get("max_drawdown"),
        "giro_medio": resultado["giro_medio"],
        "custo_anual": resultado["custo_anual"],
        "custo_que_quebra": resultado["custo_que_quebra"],
        "capacidade_mediana": resultado["capacidade_mediana"],
    }])
    config.PROTOCOL.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.TRIALS_DB))
    try:
        con.register("_linha", linha)
        con.execute("CREATE TABLE IF NOT EXISTS trials AS SELECT * FROM _linha LIMIT 0")
        # O ledger NUNCA e recriado: ele e o denominador de tentativas, e perde-lo apaga a
        # unica defesa contra teste multiplo. Coluna nova entra por ALTER; coluna que
        # sumiu do resultado fica no historico como NULL.
        atuais = {c[0] for c in con.execute("DESCRIBE trials").fetchall()}
        tipos = {"trial_id": "VARCHAR", "rodado_em": "TIMESTAMP", "nome": "VARCHAR",
                 "parametros": "VARCHAR", "meses": "BIGINT"}
        for coluna in linha.columns:
            if coluna not in atuais:
                con.execute(f"ALTER TABLE trials ADD COLUMN {coluna} "
                            f"{tipos.get(coluna, 'DOUBLE')}")
        con.execute("INSERT INTO trials BY NAME SELECT * FROM _linha")
        con.unregister("_linha")
    finally:
        con.close()


def escalar_por_vol(retornos: pd.Series, rf: pd.Series, *,
                    vol_alvo: float = 0.20, janela: int = 6,
                    teto: float = 1.5) -> pd.Series:
    """Sobrepoe controle de volatilidade: expor menos quando a estrategia esta agitada.

    POR QUE ISTO EXISTE. O momento tem uma patologia documentada e que a nossa base
    confirma: ele quebra depois de mercado em queda. Medido aqui, o excesso sobre o
    mercado e +0,72% ao mes quando os 12 meses anteriores foram de alta e **-0,74% ao mes**
    quando foram de queda -- o sinal INVERTE. E os oito piores meses do momento contra o
    mercado sao todos meses de alta violenta (setembro de 2015: mercado +34,6%, momento
    -1,0%), que e a assinatura do momentum crash de Daniel e Moskowitz: depois do bear
    market os perdedores disparam, e a carteira de vencedores fica para tras.

    A correcao conhecida nao e mudar o sinal, e mudar o TAMANHO da posicao: quando a
    volatilidade recente sobe, expor menos. O que sobra fica no CDI.

    Point-in-time: a volatilidade usada e a dos meses ANTERIORES, com `shift(1)`. Usar a
    do proprio mes seria escalar a posicao sabendo o quanto ela ia balancar.
    """
    vol = retornos.rolling(janela, min_periods=janela).std() * np.sqrt(MESES_NO_ANO)
    peso = (vol_alvo / vol.shift(1)).clip(upper=teto)
    peso = peso.fillna(1.0)
    rf_alinhado = rf.reindex(retornos.index).fillna(0.0)
    return peso * retornos + (1 - peso) * rf_alinhado


def benchmark(par: Parametros | None = None) -> dict:
    """O null certo: comprar TODO o universo elegivel, em peso igual, e segurar.

    Sem isto nenhum numero de estrategia significa nada. Um mercado que subiu 20% ao ano
    faz qualquer carteira comprada parecer genial, e o unico jeito de separar habilidade de
    mare e comparar contra a mare. E o primeiro item do protocolo de leitura de resultado
    que o Joao mandou guardar: comparar contra o null certo, nao contra zero.

    Mesmo universo, mesmo filtro de liquidez, mesmo periodo. So o custo e menor, porque
    quem nao seleciona quase nao gira.
    """
    par = par or Parametros()
    px = _painel(par)
    if px.empty:
        return {"erro": "painel vazio"}
    d = _casar_retorno_futuro(_elegiveis(px, par).sort_values(["cnpj", "ano_mes"]), px,
                              par.retorno_posicao_presa)
    custos_do_mes = {m: sub.set_index("cnpj")["custo_roundtrip"]
                     for m, sub in px.groupby("ano_mes", sort=False)}

    linhas = []
    pesos_anteriores = pd.Series(dtype=float)
    for mes, g in d.groupby("ano_mes", sort=True):
        alvo = pd.Series(1.0 / len(g), index=g["cnpj"].to_numpy())
        retorno = g.set_index("cnpj")["retorno_futuro"]
        bruto = float((alvo * retorno.reindex(alvo.index)).sum())
        giro, custo = _rebalancear(alvo, pesos_anteriores,
                                   custos_do_mes.get(mes, pd.Series(dtype=float)),
                                   float(g["custo_roundtrip"].median()))
        pesos_anteriores = _andar_com_o_mercado(alvo, retorno)
        gargalo, soma = _capacidade(g["capacidade_dia"], len(alvo))
        linhas.append({"ano_mes": g["mes_realizacao"].iloc[0], "mes_formacao": mes,
                       "retorno_bruto": bruto, "custo": custo,
                       "retorno_liquido": bruto - custo,
                       "giro": giro, "capacidade": gargalo, "capacidade_soma": soma,
                       "presas": int(g["posicao_presa"].sum()), "n": len(g)})
    serie = pd.DataFrame(linhas).set_index("ano_mes")
    rf = _risk_free_mensal()
    return {
        "nome": "BENCHMARK universo equal-weight",
        "parametros": dc.asdict(par),
        "bruto": _metricas(serie["retorno_bruto"], rf),
        "liquido": _metricas(serie["retorno_liquido"], rf),
        "giro_medio": float(serie["giro"].mean()),
        "custo_anual": float(serie["custo"].mean()) * MESES_NO_ANO,
        "capacidade_mediana": float(serie["capacidade"].median()),
        "capacidade_soma_mediana": float(serie["capacidade_soma"].median()),
        "posicoes_presas": int(serie["presas"].sum()),
        "custo_que_quebra": _custo_que_quebra(serie),
    }


def relatorio(resultado: dict) -> str:
    if "erro" in resultado:
        return f"  {resultado['nome'] if 'nome' in resultado else ''}: {resultado['erro']}"
    b, l = resultado["bruto"], resultado["liquido"]
    return "\n".join([
        f"  {resultado['nome']}",
        f"    meses               {l.get('meses')}",
        f"    retorno anual       bruto {b.get('retorno_anual', float('nan')):+.1%}"
        f"   liquido {l.get('retorno_anual', float('nan')):+.1%}",
        f"    vol anual           {l.get('vol_anual', float('nan')):.1%}",
        f"    CDI no periodo      {l.get('cdi_anual', float('nan')):+.1%}",
        f"    ACIMA DO CDI        {l.get('retorno_sobre_cdi', float('nan')):+.1%}",
        f"    sharpe (vs CDI)     {l.get('sharpe', float('nan')):.2f}",
        f"    max drawdown        {l.get('max_drawdown', float('nan')):.1%}",
        f"    giro medio/mes      {resultado['giro_medio']:.0%}",
        f"    custo anual         {resultado['custo_anual']:.1%}",
        f"    custo que quebra    {resultado['custo_que_quebra']}x",
        f"    capacidade          R$ {resultado['capacidade_mediana'] / 1e6:.2f} milhoes"
        f"   (soma: R$ {resultado.get('capacidade_soma_mediana', float('nan')) / 1e6:.1f} mi)",
        f"    posicoes presas     {resultado.get('posicoes_presas', 0)}",
    ])
