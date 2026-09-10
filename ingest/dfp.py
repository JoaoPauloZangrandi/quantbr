"""Demonstracoes Financeiras Padronizadas (DFP) da CVM -- o dado contabil.

O QUE ISTO DESTRAVA. A triagem do corpus da SSRN mediu: 173 dos papers testaveis so
dependem de dado contabil, cerca de 32% a mais do que a base alcancava. Mais concreto que
o numero: sem balanco nao existe book-to-market, nao existe E/P, nao existe qualidade nem
rentabilidade -- ou seja, metade da tabela de fatores que qualquer paper de cross-section
usa. E, para o buraco que mais atrapalha hoje, o balanco alcanca empresa que JA MORREU,
desde que ela tenha entregue formulario -- coisa que a B3 nao faz com provento.

DUAS ARMADILHAS DESTE DADO, e as duas quebram em silencio.

1. O PLANO DE CONTAS MUDA POR SETOR. Em companhia nao financeira, `2.03` e Patrimonio
   Liquido. Em banco, `2.03` e "Passivos Financeiros ao Custo Amortizado" -- outra coisa
   completamente. Casar por CODIGO de conta produziria um B/M com passivo de banco no
   numerador e ninguem perceberia. Por isso o casamento aqui e pelo NOME da conta,
   normalizado sem acento, e cada alvo lista as variantes que aparecem de fato.

2. `ESCALA_MOEDA` diz se o valor esta em unidade ou em MIL. Ignorar isso erra por mil
   vezes, e erra so em parte das empresas -- que e o pior tipo de erro, porque a serie
   continua parecendo plausivel.

POINT-IN-TIME DE VERDADE, NAO POR DEFASAGEM FIXA

O padrao da literatura e defasar o balanco em 6 meses (Fama-French) para garantir que o
dado ja era publico. E uma aproximacao grosseira: aqui a CVM informa `DT_RECEB`, a data em
que o documento efetivamente chegou. Medido em 2015: mediana de 88 dias apos a data de
referencia, p90 de 125 dias, **maximo de 964**. Uma defasagem fixa de 6 meses deixaria
passar informacao que so existiu dois anos depois, e justamente nas empresas problematicas
-- as que atrasam balanco sao as que estao em dificuldade.

Alem disso a mesma companhia entrega VERSOES (v1, v2, v3), cada uma com sua data de
recebimento: a v1 sai em fevereiro, a v3 refaz os numeros em junho. Backtest honesto usa a
versao que existia NAQUELE dia, nao a ultima. As duas colunas ficam gravadas para que a
camada de analise possa escolher -- e ter que declarar a escolha.
"""
from __future__ import annotations

import unicodedata
import zipfile

import pandas as pd

import config
import warehouse
from ingest.base import download, now_utc

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
RAW_DIR = config.RAW / "cvm_dfp"
ANO_INICIAL = 2010

# Demonstracoes que interessam. BPA = ativo, BPP = passivo e patrimonio, DRE = resultado.
# DMPL entra por causa do dividendo: e a unica fonte que alcanca empresa que JA MORREU.
# A B3 apaga o historico de provento de quem sai da bolsa; a CVM guarda o formulario.
DEMONSTRACOES = ("BPA", "BPP", "DRE", "DMPL")

# nome padronizado -> variantes que aparecem no DS_CONTA, ja sem acento e em minuscula.
# A lista e explicita de proposito: conta nova aparece como buraco, nao como valor errado.
ALVOS = {
    "ativo_total": (
        "ativo total",
    ),
    "patrimonio_liquido": (
        "patrimonio liquido consolidado",
        "patrimonio liquido",
        "patrimonio liquido consolidado atribuido a controladora",
    ),
    "lucro_liquido": (
        "lucro/prejuizo consolidado do periodo",
        "lucro/prejuizo do periodo",
        "lucro/prejuizo do exercicio",
    ),
    "receita": (
        "receita de venda de bens e/ou servicos",
        "receitas da intermediacao financeira",
        "receitas das operacoes",
    ),
    # Da DMPL. Aparecem com sinal NEGATIVO (saida de patrimonio) e sao anuais.
    "dividendos": (
        "dividendos",
    ),
    "jcp": (
        "juros sobre capital proprio",
    ),
}

# A DMPL e uma matriz: a mesma conta aparece em oito colunas de patrimonio (capital
# social, reservas, lucros acumulados...). Somar tudo contaria o mesmo dividendo varias
# vezes. So a coluna TOTAL entra.
COLUNAS_TOTAIS_DMPL = ("patrimonio liquido consolidado", "patrimonio liquido")

ESCALA = {"UNIDADE": 1.0, "MIL": 1_000.0, "MILHAO": 1_000_000.0}


def _normalizar(texto: str) -> str:
    """Sem acento, minuscula, espaco colapsado -- para o casamento nao depender de grafia."""
    if not isinstance(texto, str):
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


_MAPA = {variante: alvo for alvo, variantes in ALVOS.items() for variante in variantes}


def _ler(z: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    try:
        return pd.read_csv(z.open(nome), sep=";", encoding="latin-1", low_memory=False)
    except KeyError:
        return pd.DataFrame()


def carregar_ano(ano: int, force: bool = False) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    caminho = download(URL.format(ano=ano), RAW_DIR / f"dfp_{ano}.zip", force=force)
    z = zipfile.ZipFile(caminho)

    # Cabecalho: e dele que sai DT_RECEB, a data real em que o documento ficou publico.
    cab = _ler(z, f"dfp_cia_aberta_{ano}.csv")
    if cab.empty:
        return 0
    cab = cab[["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB"]].drop_duplicates()

    partes = []
    for dem in DEMONSTRACOES:
        for tipo, consolidado in (("con", True), ("ind", False)):
            df = _ler(z, f"dfp_cia_aberta_{dem}_{tipo}_{ano}.csv")
            if df.empty:
                continue
            df["conta"] = df["DS_CONTA"].map(_normalizar).map(_MAPA)
            df = df.dropna(subset=["conta"])
            if df.empty:
                continue
            # A DFP traz o exercicio corrente e o anterior na mesma linha de arquivo.
            # So o ULTIMO e o exercicio de referencia; o penultimo repetiria o ano passado.
            df = df[df["ORDEM_EXERC"].map(_normalizar) == "ultimo"]
            if dem == "DMPL" and "COLUNA_DF" in df.columns:
                coluna = "patrimonio liquido consolidado" if consolidado else "patrimonio liquido"
                df = df[df["COLUNA_DF"].map(_normalizar) == coluna]
            elif dem == "DMPL":
                continue
            df["consolidado"] = consolidado
            df["demonstracao"] = dem
            partes.append(df)

    if not partes:
        return 0
    d = pd.concat(partes, ignore_index=True)

    d["escala"] = d["ESCALA_MOEDA"].map(_normalizar).str.upper().map(ESCALA).fillna(1.0)
    d["valor"] = pd.to_numeric(d["VL_CONTA"], errors="coerce") * d["escala"]
    d = d.dropna(subset=["valor"])

    d = d.merge(cab, on=["CNPJ_CIA", "DT_REFER", "VERSAO"], how="left")
    saida = pd.DataFrame({
        "cnpj": d["CNPJ_CIA"],
        "dt_refer": pd.to_datetime(d["DT_REFER"], errors="coerce"),
        "dt_fim_exerc": pd.to_datetime(d["DT_FIM_EXERC"], errors="coerce"),
        "dt_receb": pd.to_datetime(d["DT_RECEB"], errors="coerce"),
        "versao": pd.to_numeric(d["VERSAO"], errors="coerce"),
        "consolidado": d["consolidado"],
        "demonstracao": d["demonstracao"],
        "conta": d["conta"],
        "ds_conta": d["DS_CONTA"],
        "valor": d["valor"],
        "ano_dfp": ano,
    })
    # Uma linha por (empresa, referencia, versao, consolidado, conta). Quando o mesmo
    # nome de conta aparece mais de uma vez na mesma demonstracao, fica o maior valor
    # absoluto -- e o total, nao a subconta.
    # Dividendo e JCP saem da DMPL com sinal negativo (saida de patrimonio). Vira valor
    # positivo: e quanto a empresa distribuiu, e e assim que dividend yield se le.
    saida.loc[saida["conta"].isin(("dividendos", "jcp")), "valor"] = (
        saida.loc[saida["conta"].isin(("dividendos", "jcp")), "valor"].abs())
    saida = (saida.sort_values("valor", key=lambda s: s.abs(), ascending=False)
                  .drop_duplicates(["cnpj", "dt_refer", "versao", "consolidado", "conta"]))
    saida["_source_file"] = f"cvm/DFP {ano}"
    saida["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        warehouse.replace_partition(con, "cvm_dfp", saida, key="ano_dfp", value=ano)
    return len(saida)


def carregar(anos: list[int] | None = None) -> int:
    anos = anos or list(range(ANO_INICIAL, pd.Timestamp.today().year + 1))
    total = 0
    for ano in anos:
        # O ano corrente e reescrito conforme as empresas entregam.
        n = carregar_ano(ano, force=(ano >= pd.Timestamp.today().year))
        print(f"  DFP {ano}: {n:,} linhas")
        total += n
    return total


if __name__ == "__main__":
    print(f"DFP total: {carregar():,} linhas")
