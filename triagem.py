"""Triagem do corpus: o que da para testar em acoes brasileiras, e com qual dado.

O QUE ESTE MODULO RESPONDE

Duas perguntas, nesta ordem:

  1. este paper e um estudo empirico de RETORNO DE ACAO? (a maior parte do Financial
     Economics Network nao e -- tem direito societario, banco, cripto, imovel, seguro)
  2. se e, de que DADO ele precisa para ser replicado?

A segunda pergunta e a que decide investimento de esforco. Em vez de adivinhar se vale a
pena montar base contabil, a gente conta quantos papers relevantes precisam dela.

COMO CLASSIFICA, E POR QUE ISSO E HEURISTICA E NAO VERDADE

Por palavra-chave em titulo, abstract (quando existe) e topicos do OpenAlex. Nao ha
abstract em massa: a SSRN bloqueia raspagem (403 do Cloudflare) e o OpenAlex so tem
abstract em 2% dos registros dela. Entao a classificacao acerta o grosso e erra nas
bordas, e serve para DIMENSIONAR, nao para decidir paper a paper.

Todo conjunto de palavras esta escrito aqui embaixo, em aberto, para poder ser discutido e
corrigido. Nenhuma classificacao acontece dentro de um modelo opaco.

AS CATEGORIAS DE DADO seguem o que a gente tem e o que teria de construir:

    preco_volume   -> temos. Momento, reversao, volatilidade, liquidez, sazonalidade
    tamanho        -> temos, de 2011 em diante. Ordenacoes por valor de mercado
    contabil       -> NAO temos. Valor, rentabilidade, investimento, accruals, lucro
    posse          -> nao temos, mas o Joao ja construiu isso antes (CDA da CVM)
    opcoes         -> nao temos. Volatilidade implicita, skew, premio de risco de variancia
    texto          -> nao temos. Noticia, sentimento, tom, LLM
    intradiario    -> nao temos. Alta frequencia, livro de ofertas, microestrutura
"""
from __future__ import annotations

import re

import pandas as pd

import warehouse

# --------------------------------------------------------------------------------
# 1) E estudo empirico de retorno de acao?
# --------------------------------------------------------------------------------
SINAIS_DE_RETORNO = [
    "stock return", "stock price", "cross-section", "cross section", "anomal",
    "asset pricing", "expected return", "risk premi", "factor model", "alpha",
    "portfolio", "momentum", "reversal", "predictab", "trading strateg",
    "mispricing", "market efficiency", "equity return", "abnormal return",
    "excess return", "return predict", "stock market", "equity market",
]

# Assunto que nao e retorno de acao. Testado ANTES, porque "bank capital" pode conter
# "portfolio" sem ser estudo de secao transversal de acao.
FORA_DE_ESCOPO = [
    "corporate governance", "board of director", "executive compensation", "ceo pay",
    "bank capital", "basel", "deposit insurance", "bank run", "lending",
    "monetary policy", "central bank", "inflation", "exchange rate", "sovereign debt",
    "municipal bond", "insurance", "pension reform", "microfinance", "tax polic",
    "law and economics", "securities regulation", "litigation", "bankruptcy law",
    "cryptocurrenc", "bitcoin", "blockchain", "defi", "stablecoin", "nft",
    "real estate", "housing market", "mortgage", "reit",
    "private equity", "venture capital", "crowdfunding",
    "climate polic", "financial literacy", "financial inclusion",
]

# --------------------------------------------------------------------------------
# 2) De que dado o teste precisa?
# --------------------------------------------------------------------------------
NECESSIDADES = {
    "contabil": [
        "book-to-market", "book to market", "value premium", "value factor",
        "earnings", "accrual", "asset growth", "investment factor", "gross profit",
        "cash flow", "balance sheet", "financial statement", "fundamental analysis",
        "leverage", "f-score", "piotroski", "quality minus junk", "net issuance",
        "capital expenditure", "book value", "valuation ratio", "price-to-earnings",
        "price to earnings", "earnings announcement", "earnings surprise",
        "analyst forecast", "return on equity", "return on asset",
        # Modelos que sao definidos por caracteristica contabil, mesmo sem citar a conta:
        "five-factor", "five factor model", "q-factor", "q factor", "hml",
        # ATENCAO: "profitab" sozinho e armadilha -- casa com "profitable strategy",
        # que nao tem nada de contabil. Pego ao vivo em "A Profitable Day Trading
        # Strategy", classificado errado como se precisasse de balanco. So valem as
        # formas em que profitability e a CARACTERISTICA da empresa:
        "profitability factor", "profitability premium", "gross profitability",
        "operating profitability", "profitability anomaly", "profitability and",
    ],
    "opcoes": [
        "option", "implied volatilit", "variance risk premi", "skew", "straddle",
        "vix", "derivative", "volatility surface",
    ],
    "posse": [
        "institutional ownership", "institutional investor", "mutual fund",
        "hedge fund holding", "13f", "fund flow", "ownership structure",
        "common ownership", "index inclusion", "passive investing",
    ],
    "texto": [
        "sentiment", "textual", "news", "media coverage", "tone", "social media",
        "twitter", "reddit", "language model", "chatgpt", "llm", "narrative",
        "disclosure tone", "10-k text",
    ],
    "intradiario": [
        "high-frequency", "high frequency", "intraday", "order book", "limit order",
        "microstructure", "tick data", "bid-ask spread", "price impact", "order flow",
    ],
    "tamanho": [
        "size effect", "small cap", "firm size", "market capitalization", "smb",
    ],
    "preco_volume": [
        "momentum", "reversal", "volatilit", "liquidit", "beta", "technical analysis",
        "moving average", "52-week", "trend follow", "seasonalit", "calendar effect",
        "turnover", "trading volume", "idiosyncratic", "lottery", "maximum daily return",
        "short interest", "amihud",
    ],
}

# O que ja existe em acoes_diario
TEMOS = {"preco_volume", "tamanho"}


def _texto(linha) -> str:
    # Colunas vindas do LEFT JOIN chegam como NaN (float), nao como None -- daí o
    # isinstance em vez de um simples `or ""`.
    partes = (linha.get("titulo"), linha.get("titulo_oa"),
              linha.get("abstract"), linha.get("topicos"))
    return " ".join(p.lower() for p in partes if isinstance(p, str) and p)


def _bate(texto: str, termos: list[str]) -> list[str]:
    return [t for t in termos if t in texto]


def classificar() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        tem_oa = warehouse.table_exists(con, "papers_openalex")
        sql = """
            SELECT s.ssrn_id, s.titulo, s.data_aprovacao, s.downloads, s.url
                   {extra}
            FROM papers_ssrn s
            {juncao}
        """.format(
            extra=", o.titulo_oa, o.abstract, o.topicos, o.citacoes" if tem_oa else
                  ", NULL AS titulo_oa, NULL AS abstract, NULL AS topicos, NULL AS citacoes",
            juncao="LEFT JOIN papers_openalex o USING (ssrn_id)" if tem_oa else "",
        )
        df = con.execute(sql).df()

    registros = []
    for linha in df.to_dict("records"):
        t = _texto(linha)
        fora = _bate(t, FORA_DE_ESCOPO)
        sobre_retorno = bool(_bate(t, SINAIS_DE_RETORNO))

        necessidades = {k: _bate(t, v) for k, v in NECESSIDADES.items()}
        precisa = [k for k, v in necessidades.items() if v]

        if not sobre_retorno:
            categoria = "nao_e_retorno_de_acao"
        elif fora and not precisa:
            categoria = "fora_de_escopo"
        elif not precisa:
            categoria = "retorno_sem_dado_identificado"
        elif set(precisa) <= TEMOS:
            categoria = "testavel_com_o_que_temos"
        else:
            faltando = sorted(set(precisa) - TEMOS)
            categoria = "precisa_de_" + "+".join(faltando)

        registros.append({
            **{k: linha[k] for k in ("ssrn_id", "titulo", "data_aprovacao",
                                     "downloads", "citacoes", "url")},
            "sobre_retorno": sobre_retorno,
            "precisa": " ".join(sorted(precisa)),
            "categoria": categoria,
            "termos_achados": " | ".join(
                f"{k}:{','.join(v[:2])}" for k, v in necessidades.items() if v)[:200],
        })

    res = pd.DataFrame(registros)
    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS papers_triagem")
        con.register("_t", res)
        con.execute("CREATE TABLE papers_triagem AS SELECT * FROM _t")
        con.unregister("_t")
    return res


def relatorio(minimo_downloads: int = 0) -> None:
    pd.set_option("display.width", 210)
    pd.set_option("display.max_colwidth", 66)
    with warehouse.connect(read_only=True) as con:
        df = con.execute("SELECT * FROM papers_triagem").df()

    if minimo_downloads:
        df = df[df["downloads"].fillna(0) >= minimo_downloads]

    print("=" * 78)
    print(f"TRIAGEM DE {len(df):,} PAPERS"
          + (f" com pelo menos {minimo_downloads:,} downloads" if minimo_downloads else ""))
    print("=" * 78)
    tab = (df["categoria"].value_counts().rename("papers").to_frame()
           .assign(pct=lambda d: (100 * d["papers"] / len(df)).round(1)))
    print(tab.to_string())

    empiricos = df[df["sobre_retorno"]]
    print(f"\nDos {len(df):,}, {len(empiricos):,} sao estudo de retorno de acao "
          f"({100*len(empiricos)/max(len(df),1):.0f}%).")

    print("\n" + "=" * 78)
    print("ENTRE OS DE RETORNO: qual dado cada um exige")
    print("=" * 78)
    for chave in NECESSIDADES:
        n = empiricos["precisa"].str.contains(chave, na=False).sum()
        marca = "TEMOS" if chave in TEMOS else "falta"
        print(f"  {chave:<14} {n:>6,}  ({100*n/max(len(empiricos),1):>4.1f}%)  {marca}")

    so_temos = empiricos[empiricos["categoria"] == "testavel_com_o_que_temos"]
    so_falta_contabil = empiricos[empiricos["categoria"] == "precisa_de_contabil"]
    print(f"\n  testaveis hoje, sem dado novo          : {len(so_temos):>6,}")
    print(f"  destravariam SO com dado contabil      : {len(so_falta_contabil):>6,}")


if __name__ == "__main__":
    import sys

    classificar()
    relatorio()
    if "--relevantes" in sys.argv:
        print("\n\n")
        relatorio(minimo_downloads=2000)
