"""Mede o efeito de cada etapa do tratamento da base. Nao conserta nada.

Regra 6 do projeto: auditoria MEDE, nao conserta. Correcao e decisao humana e vira
arquivo versionado. Este modulo existe para que nenhuma etapa do tratamento seja aceita
por impressao -- toda mudanca de numero tem que ser explicada por uma causa nomeada.

Por que uma linha de base congelada: as etapas 1 (unidade de cotacao) e 6 (retorno como
primitiva) mudam o numero de TODA a base. Sem uma copia do estado anterior nao da para
separar "mudou porque consertamos" de "mudou porque quebramos". A copia e barata: uma
tabela a mais no mesmo warehouse, reconstruivel a partir de data/raw/ se for preciso.

A licao que motivou o desenho: em 09/09/2026 o detector de split foi corrigido e o
contador de saltos residuais SUBIU (438 -> 446 quedas). Parecia piora. Era o contrario --
o detector antigo casava razao grande com fracao meia-quebrada (AMER3 com 13/3) e
apagava da serie a queda real da Americanas. O numero agregado mentiu; o diff caso a caso
contou a verdade. Por isso `comparar` devolve tambem o conjunto de saltos que sumiu e o
que apareceu, nao so a contagem.

Uso:
    python -m master.auditoria_tratamento --congelar          # antes de mexer
    python -m master.auditoria_tratamento --comparar <tabela> # depois de mexer
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

import config
import warehouse

# Limiares de "salto residual". Um desdobramento nao detectado aparece como queda enorme;
# um grupamento nao detectado, como alta enorme. Os cortes sao assimetricos de proposito:
# -45% em um pregao ja e raro em acao liquida, mas +90% e o espelho de -47%, e queremos
# os dois lados com a mesma severidade.
QUEDA_SUSPEITA = -0.45
ALTA_SUSPEITA = 0.90

PREFIXO_BASE = "acoes_diario_base_"


def _nome_congelado(hoje: dt.date | None = None) -> str:
    hoje = hoje or dt.date.today()
    return f"{PREFIXO_BASE}{hoje:%Y%m%d}"


def congelar(nome: str | None = None) -> str:
    """Copia `acoes_diario` para uma tabela datada, que nunca mais e escrita."""
    nome = nome or _nome_congelado()
    with warehouse.connect() as con:
        if not warehouse.table_exists(con, "acoes_diario"):
            raise RuntimeError("acoes_diario nao existe; nada a congelar")
        if warehouse.table_exists(con, nome):
            n = con.execute(f"SELECT count(*) FROM {nome}").fetchone()[0]
            print(f"  {nome} ja existe ({n:,} linhas) -- mantida como esta")
            return nome
        con.execute(f"CREATE TABLE {nome} AS SELECT * FROM acoes_diario")
        n = con.execute(f"SELECT count(*) FROM {nome}").fetchone()[0]
    print(f"  linha de base congelada: {nome} ({n:,} linhas)")
    return nome


def _coluna_de_preco(con, tabela: str) -> str:
    """Qual coluna usar como preco ajustado. Sobrevive a renomeacao das etapas."""
    cols = {c[0] for c in con.execute(f"DESCRIBE {tabela}").fetchall()}
    for candidata in ("fechamento_ajustado", "fechamento"):
        if candidata in cols:
            return candidata
    raise RuntimeError(f"{tabela} nao tem coluna de preco reconhecida")


def _tem(con, tabela: str, coluna: str) -> bool:
    return coluna in {c[0] for c in con.execute(f"DESCRIBE {tabela}").fetchall()}


def metricas(tabela: str = "acoes_diario") -> dict:
    """Retrato numerico de uma versao da base."""
    with warehouse.connect(read_only=True) as con:
        preco = _coluna_de_preco(con, tabela)
        m: dict = {}
        m["linhas"], m["tickers"], m["ini"], m["fim"] = con.execute(f"""
            SELECT count(*), count(DISTINCT ticker), min(data), max(data) FROM {tabela}
        """).fetchone()

        # Saltos residuais: o que sobrou sem ajuste. So em acao (on/pn) -- unit e ETF tem
        # dinamica propria e poluiriam a contagem.
        m["quedas"], m["altas"] = con.execute(f"""
            WITH r AS (
                SELECT {preco} / lag({preco}) OVER (PARTITION BY ticker ORDER BY data) - 1 AS ret
                FROM {tabela} WHERE classe IN ('on','pn')
            )
            SELECT count(*) FILTER (WHERE ret < {QUEDA_SUSPEITA}),
                   count(*) FILTER (WHERE ret > {ALTA_SUSPEITA})
            FROM r
        """).fetchone()

        # Cobertura de provento, PONDERADA POR VOLUME. Contagem simples de tickers mente:
        # 300 papeis ilíquidos sem provento pesam menos que a Ambev sozinha.
        if _tem(con, tabela, "tem_provento"):
            m["cob_provento_pct"] = con.execute(f"""
                WITH t AS (SELECT ticker, sum(volume) vol, bool_or(tem_provento) tem
                           FROM {tabela} GROUP BY 1)
                SELECT round(100.0 * sum(vol) FILTER (WHERE tem) / nullif(sum(vol),0), 1) FROM t
            """).fetchone()[0]

        # Cobertura de identidade, ponderada por pregoes (criterio de auditoria.py: um
        # papel com 5.000 pregoes fora do universo distorce mais que 50 com 20).
        if _tem(con, tabela, "cnpj"):
            m["cob_cnpj_pct"] = con.execute(f"""
                SELECT round(100.0 * count(*) FILTER (WHERE cnpj IS NOT NULL) / count(*), 1)
                FROM {tabela}
            """).fetchone()[0]

        if _tem(con, tabela, "regime"):
            m["regimes"] = dict(con.execute(f"""
                SELECT regime, count(DISTINCT ticker) FROM {tabela} GROUP BY 1
            """).fetchall())

        # Papeis truncados: ultimo pregao no painel bem antes do ultimo no COTAHIST.
        # E o sintoma do filtro de codbdi apagando empresa em recuperacao judicial.
        m["papeis_truncados"] = con.execute(f"""
            WITH p AS (SELECT ticker, max(data) fim FROM {tabela} GROUP BY 1),
                 c AS (SELECT ticker, max(data) fim FROM b3_cotahist WHERE tpmerc='010' GROUP BY 1)
            SELECT count(*) FROM p JOIN c USING (ticker) WHERE c.fim > p.fim + 5
        """).fetchone()[0]
    return m


def _saltos(con, tabela: str) -> set[tuple]:
    preco = _coluna_de_preco(con, tabela)
    df = con.execute(f"""
        WITH r AS (
            SELECT ticker, data,
                   {preco} / lag({preco}) OVER (PARTITION BY ticker ORDER BY data) - 1 AS ret
            FROM {tabela} WHERE classe IN ('on','pn')
        )
        SELECT ticker, data FROM r WHERE ret < {QUEDA_SUSPEITA} OR ret > {ALTA_SUSPEITA}
    """).df()
    return set(map(tuple, df.values))


def comparar(antes: str, depois: str = "acoes_diario", *, detalhe: int = 10) -> pd.DataFrame:
    """Antes x depois, metrica a metrica, MAIS o diff caso a caso dos saltos.

    O diff e a parte que importa. O agregado ja mentiu uma vez (ver docstring do modulo):
    o que separa conserto de estrago e saber QUAIS saltos sumiram e quais nasceram.
    """
    ma, md = metricas(antes), metricas(depois)
    chaves = sorted(set(ma) | set(md))
    tabela = pd.DataFrame(
        [{"metrica": k, "antes": ma.get(k), "depois": md.get(k)} for k in chaves]
    )
    print(f"\n{antes}  ->  {depois}\n")
    print(tabela.to_string(index=False))

    with warehouse.connect(read_only=True) as con:
        sa, sd = _saltos(con, antes), _saltos(con, depois)
        resolvidos, novos = sa - sd, sd - sa
        print(f"\nsaltos resolvidos: {len(resolvidos):,}   |   saltos novos: {len(novos):,}")
        for titulo, conjunto in (("RESOLVIDOS", resolvidos), ("NOVOS", novos)):
            if not conjunto:
                continue
            df = pd.DataFrame(sorted(conjunto)[:detalhe], columns=["ticker", "data"])
            print(f"\n  {titulo} (amostra de {min(detalhe, len(conjunto))}):")
            print(df.to_string(index=False))
    return tabela


def residuo_por_causa(tabela: str = "acoes_diario") -> pd.DataFrame:
    """Classifica o salto que sobrou. Contar nao basta -- o numero agregado ja mentiu.

    Quatro causas, e so a primeira e "erro do detector":

      papel_de_centavos      -- o preco cotado anterior estava abaixo de R$1, onde o tick
                                de R$0,01 domina e fracao redonda nao prova nada. E a
                                populacao que MAIS faz grupamento, justamente porque esta
                                barata. Precisa de gabarito externo, nao de mais folga.
      regime_especial        -- papel em recuperacao judicial ou leilao. Entrou na base na
                                Etapa 2; antes nem existia para ser contado.
      dia_ex_movimentado     -- o detector viu a razao, achou o inteiro certo, e reprovou
                                por pouco (erro entre a tolerancia e 10%). MGLU3 8:1 erra
                                5,2%. So a contagem de acoes da CVM resolve.
      nao_classificado       -- inclui a queda real, que e para ficar assim mesmo. A AMER3
                                em 12/01/2023 caiu 77% de verdade.
    """
    from master import eventos

    ev = eventos.detectar()
    ev = ev[ev["confianca"].isin(("descartado", "preco_de_centavos", "baixa"))]
    ev = ev[["ticker", "data", "erro_relativo", "confianca"]].copy()
    ev["data"] = pd.to_datetime(ev["data"])

    with warehouse.connect(read_only=True) as con:
        preco = _coluna_de_preco(con, tabela)
        tem_regime = _tem(con, tabela, "regime")
        saltos = con.execute(f"""
            WITH r AS (
                SELECT ticker, data, {'regime' if tem_regime else "'normal' AS regime"},
                       lag(fechamento) OVER (PARTITION BY ticker ORDER BY data) AS fech_ant,
                       {preco} / lag({preco}) OVER (PARTITION BY ticker ORDER BY data)
                         - 1 AS ret
                FROM {tabela} WHERE classe IN ('on','pn')
            )
            SELECT ticker, data, regime, fech_ant, ret FROM r
            WHERE ret < {QUEDA_SUSPEITA} OR ret > {ALTA_SUSPEITA}
        """).df()

    saltos["data"] = pd.to_datetime(saltos["data"])
    j = saltos.merge(ev, on=["ticker", "data"], how="left")

    def _causa(linha) -> str:
        if linha["confianca"] == "preco_de_centavos" or (
                pd.notna(linha["fech_ant"]) and linha["fech_ant"] < 1.0):
            return "papel_de_centavos"
        if linha["regime"] != "normal":
            return "regime_especial"
        if pd.notna(linha["erro_relativo"]) and linha["erro_relativo"] <= 0.10:
            return "dia_ex_movimentado"
        return "nao_classificado"

    j["causa"] = j.apply(_causa, axis=1)
    resumo = (j.groupby("causa")
                .agg(saltos=("ticker", "size"), papeis=("ticker", "nunique"))
                .sort_values("saltos", ascending=False).reset_index())
    print(resumo.to_string(index=False))
    return j


def pendentes_identidade(minimo_pregoes: int = 1) -> pd.DataFrame:
    """Emite o que a resolucao automatica NAO conseguiu -- para decisao humana.

    Regra 6: auditoria mede, nao conserta. Esta funcao escreve em
    `crosswalk/pendentes_identidade.csv`, que e material de trabalho e NAO e a fonte;
    a fonte e `crosswalk/identidade.csv`, preenchida a mao, com evidencia por linha.

    O buraco e estrutural e conhecido: o `Codigo_Negociacao` do FCA da CVM esta vazio de
    2010 a 2017, entao quem morreu antes de 2018 nao tem ponte oficial. Ordenado por
    pregoes porque um papel com 5.000 pregoes fora do universo distorce muito mais que
    50 papeis com 20 -- e o mesmo criterio de `auditoria.cobertura_identidade`.
    """
    with warehouse.connect(read_only=True) as con:
        df = con.execute(f"""
            SELECT m.ticker, m.classe_papel, m.primeiro_pregao, m.ultimo_pregao,
                   m.n_pregoes, m.emissor_isin, m.isin,
                   (SELECT any_value(empresa) FROM acoes_diario a
                     WHERE a.ticker = m.ticker) AS nome_no_pregao
            FROM master_ticker m
            WHERE m.cnpj IS NULL AND m.n_pregoes >= {minimo_pregoes}
              AND m.classe_papel IN ('acao', 'unit_etf_fii')
            ORDER BY m.n_pregoes DESC
        """).df()
    destino = config.CROSSWALK / "pendentes_identidade.csv"
    df.to_csv(destino, index=False)
    print(f"  {len(df):,} tickers sem CNPJ -> {destino}")
    if not df.empty:
        print(f"  {df.n_pregoes.sum():,.0f} pregoes envolvidos; "
              f"{(df.ultimo_pregao < pd.Timestamp('2018-01-01')).sum():,} morreram antes de 2018")
    return df


def main() -> int:
    p = argparse.ArgumentParser(description="mede o efeito das etapas do tratamento")
    p.add_argument("--congelar", action="store_true", help="copia o estado atual")
    p.add_argument("--comparar", metavar="TABELA", help="compara essa tabela com a atual")
    p.add_argument("--metricas", metavar="TABELA", nargs="?", const="acoes_diario",
                   help="so o retrato de uma tabela")
    p.add_argument("--pendentes", action="store_true",
                   help="emite o CSV de tickers sem CNPJ, para decisao humana")
    p.add_argument("--residuo", action="store_true",
                   help="classifica os saltos que sobraram, por causa")
    a = p.parse_args()

    if a.congelar:
        congelar()
    if a.comparar:
        comparar(a.comparar)
    if a.pendentes:
        pendentes_identidade()
    if a.residuo:
        residuo_por_causa()
    if a.metricas:
        for k, v in metricas(a.metricas).items():
            print(f"  {k:22s} {v}")
    if not (a.congelar or a.comparar or a.metricas or a.pendentes or a.residuo):
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
