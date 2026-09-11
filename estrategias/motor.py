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
    # Filtro de negociabilidade. O default nao e neutro: R$500 mil por dia ja exclui a
    # cauda onde o custo de ida e volta passa de 4% e nenhuma estrategia sobrevive.
    liquidez_minima: float = 500_000.0
    # Retorno usado. 'retorno_total' inclui provento; 'retorno_qtd' so ajusta quantidade.
    # A escolha muda o resultado e por isso e explicita -- regra do projeto: nao existe
    # "o preco".
    coluna_retorno: str = "retorno_total"
    mes_inicial: str = "2010-01"   # antes disso nao ha valor de mercado nem balanco
    mes_final: str = "2026-09"
    long_short: bool = False       # False = so comprado; True = compra topo, vende fundo


def _painel(par: Parametros) -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        return con.execute(f"""
            SELECT cnpj, ano_mes, ticker, nome,
                   {par.coluna_retorno} AS retorno,
                   volume_mediano, custo_roundtrip, capacidade_dia,
                   valor_mercado_empresa, pregoes_no_mes,
                   motivo_saida, retorno_delisting
            FROM emissor_mensal
            WHERE ano_mes BETWEEN '{par.mes_inicial}' AND '{par.mes_final}'
              AND volume_mediano >= {par.liquidez_minima}
            ORDER BY cnpj, ano_mes
        """).df()


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

    d = px.merge(sinal.dropna(subset=["sinal"]), on=["cnpj", "ano_mes"], how="inner")
    if d.empty:
        return {"erro": "sinal nao casou com o painel"}

    # O retorno do mes SEGUINTE. Feito aqui, uma vez, para ninguem esquecer.
    d = d.sort_values(["cnpj", "ano_mes"])
    d["retorno_futuro"] = d.groupby("cnpj")["retorno"].shift(-1)
    # Papel que sai da base leva o retorno de delisting no ultimo mes, em vez de sumir.
    ultimo = d["retorno_futuro"].isna() & d["retorno_delisting"].notna()
    d.loc[ultimo, "retorno_futuro"] = d.loc[ultimo, "retorno_delisting"]
    d = d.dropna(subset=["retorno_futuro"])

    linhas, carteira_anterior = [], set()
    for mes, g in d.groupby("ano_mes", sort=True):
        if len(g) < par.n_papeis * 2:
            continue   # cross-section pequena demais para formar carteira e contraparte
        g = g.sort_values("sinal", ascending=False)
        topo = g.head(par.n_papeis)
        bruto = float(topo["retorno_futuro"].mean())
        if par.long_short:
            fundo = g.tail(par.n_papeis)
            bruto -= float(fundo["retorno_futuro"].mean())

        atual = set(topo["ticker"])
        # Giro: fracao da carteira que mudou. Entrar e sair custa uma ida-e-volta,
        # dividida entre as duas pontas -- por isso a metade.
        trocas = len(atual - carteira_anterior)
        giro = trocas / par.n_papeis if carteira_anterior else 1.0
        custo_medio = float(topo["custo_roundtrip"].median())
        custo = giro * custo_medio
        carteira_anterior = atual

        linhas.append({
            "ano_mes": mes,
            "retorno_bruto": bruto,
            "custo": custo,
            "retorno_liquido": bruto - custo,
            "giro": giro,
            "capacidade": float(topo["capacidade_dia"].sum()) * 5,  # 5 pregoes para montar
            "n": len(topo),
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
        "capacidade_mediana": float(serie["capacidade"].median()),
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
    d = px.sort_values(["cnpj", "ano_mes"]).copy()
    d["retorno_futuro"] = d.groupby("cnpj")["retorno"].shift(-1)
    ultimo = d["retorno_futuro"].isna() & d["retorno_delisting"].notna()
    d.loc[ultimo, "retorno_futuro"] = d.loc[ultimo, "retorno_delisting"]
    d = d.dropna(subset=["retorno_futuro"])

    linhas, anterior = [], set()
    for mes, g in d.groupby("ano_mes", sort=True):
        atual = set(g["ticker"])
        giro = len(atual - anterior) / max(len(atual), 1) if anterior else 1.0
        custo = giro * float(g["custo_roundtrip"].median())
        anterior = atual
        linhas.append({"ano_mes": mes, "retorno_bruto": float(g["retorno_futuro"].mean()),
                       "custo": custo, "retorno_liquido": float(g["retorno_futuro"].mean()) - custo,
                       "giro": giro, "capacidade": float(g["capacidade_dia"].sum()) * 5,
                       "n": len(g)})
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
        f"    capacidade          R$ {resultado['capacidade_mediana'] / 1e6:.1f} milhoes",
    ])
