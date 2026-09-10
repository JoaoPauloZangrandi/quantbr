"""Securities master: quem e quem, ao longo do tempo.

O problema que este modulo resolve: ticker nao e identidade. TRPL3 e ISAE3 sao a mesma
empresa (CNPJ 02.998.611/0001-04) antes e depois de uma troca de nome; RRRP3 deixou de
existir quando a 3R Petroleum virou Brava Energia. Um backtest que trata isso como duas
empresas parte a serie no meio e inventa uma "morte" que nunca houve.

A chave estavel e o CNPJ. Nome muda, ticker muda, ISIN muda; CNPJ nao.

Tres tabelas produzidas:
  master_empresa   -- uma linha por CNPJ: nome atual, situacao do registro, data e
                      motivo de cancelamento (fusao e diferente de fechar capital).
  master_ticker    -- uma linha por ticker: a que CNPJ pertence, em que anos a CVM o
                      registrou, e o primeiro/ultimo pregao realmente observado no
                      COTAHIST. Os dois lados importam: a CVM diz o que deveria existir,
                      o COTAHIST diz o que de fato negociou.
  master_sucessao  -- para cada CNPJ com mais de um ticker, a cadeia em ordem de tempo.

Limitacao registrada de proposito: o FCA comeca em 2010. Antes disso nao ha ponte
ticker<->CNPJ por esta via, e o vinculo tem que sair do proprio COTAHIST (via ISIN) ou
ficar marcado como desconhecido. Nao inventar vinculo que a fonte nao sustenta.
"""
from __future__ import annotations

import pandas as pd

import config
import warehouse

# O que conta como acao no nosso universo. Debenture, nota comercial etc. ficam fora.
TIPOS_ACAO = (
    "Ações Ordinárias",
    "Ações Preferenciais",
    "Units",
    "Certificados de Depósito de Ações",
)


def _crosswalk_identidade() -> pd.DataFrame:
    """Le as decisoes humanas de ticker->CNPJ. Nunca escreve.

    Regra 6 do projeto. O arquivo pode estar vazio -- e o estado normal ate alguem
    revisar a lista de pendentes que a auditoria emite.
    """
    caminho = config.CROSSWALK / "identidade.csv"
    if not caminho.exists():
        return pd.DataFrame(columns=["ticker", "cnpj"])
    df = pd.read_csv(caminho, dtype=str).fillna("")
    df = df[(df.get("ticker", "") != "") & (df.get("cnpj", "") != "")]
    return df[["ticker", "cnpj"]].drop_duplicates("ticker")


def construir() -> dict[str, int]:
    with warehouse.connect() as con:
        snap = con.execute("SELECT max(_snapshot) FROM cvm_cadastro").fetchone()[0]

        # ---------------- master_empresa ----------------
        # O cad_cia_aberta e um HISTORICO DE REGISTRO, nao uma linha por empresa: 140 CNPJs
        # aparecem 2 ou 3 vezes. Dois motivos reais, ambos verificados no caso da Vibra
        # (CNPJ 34.274.233/0001-02): (a) uma linha por tipo de mercado (BOLSA e BALCAO
        # ORGANIZADO) e (b) episodios distintos de registro -- ela teve registro cancelado
        # em 2003 por OPA e voltou a registrar em 2017 ao reabrir capital.
        # Sem deduplicar, o join multiplica linhas e a MESMA empresa sai como 'ativa' e
        # 'cancelada_outro' ao mesmo tempo. Ficamos com o episodio mais recente, com
        # preferencia por BOLSA, e guardamos o passado como flag em vez de descartar.
        con.execute("DROP TABLE IF EXISTS master_empresa")
        con.execute(
            """
            CREATE TABLE master_empresa AS
            WITH ranqueado AS (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY CNPJ_CIA
                           ORDER BY DT_INI_SIT DESC NULLS LAST,
                                    CASE WHEN TP_MERC = 'BOLSA' THEN 0 ELSE 1 END
                       ) AS rn,
                       count(*)      OVER (PARTITION BY CNPJ_CIA) AS n_registros,
                       max(CASE WHEN SIT = 'CANCELADA' THEN 1 ELSE 0 END)
                                     OVER (PARTITION BY CNPJ_CIA) AS ja_teve_cancelamento
                FROM cvm_cadastro
                WHERE _snapshot = ?
            )
            SELECT
                CNPJ_CIA           AS cnpj,
                n_registros,
                ja_teve_cancelamento::BOOLEAN AS ja_teve_cancelamento,
                DENOM_SOCIAL       AS nome_atual,
                CD_CVM             AS codigo_cvm,
                SIT                AS situacao_registro,
                DT_CANCEL          AS data_cancelamento,
                MOTIVO_CANCEL      AS motivo_cancelamento,
                SETOR_ATIV         AS setor,
                CONTROLE_ACIONARIO AS controle,
                -- Fusao deixa sucessor; fechamento de capital nao. O backtest encerra a
                -- posicao de um jeito diferente em cada caso, entao a distincao entra aqui.
                CASE
                    WHEN SIT <> 'CANCELADA' THEN 'ativa'
                    WHEN upper(MOTIVO_CANCEL) LIKE '%INCORPORA%' THEN 'incorporada'
                    WHEN upper(MOTIVO_CANCEL) LIKE '%VOLUNT%'    THEN 'fechou_capital'
                    -- Instrucao CVM 361/02 e a que rege a OPA. Cancelamento por
                    -- "atendimento" a ela e fechamento de capital via oferta: o acionista
                    -- recebeu dinheiro, nao perdeu a posicao. Sao 218 companhias.
                    WHEN MOTIVO_CANCEL LIKE '%361%'              THEN 'fechou_capital'
                    -- Extincao e liquidacao: nao ha sucessor nem oferta. E perda.
                    WHEN upper(MOTIVO_CANCEL) LIKE '%EXTIN%'
                      OR upper(MOTIVO_CANCEL) LIKE '%LIQUIDA%'   THEN 'liquidada'
                    -- Cancelamento de oficio: a CVM cancela o registro da companhia que
                    -- parou de prestar informacao. Na pratica a posicao fica sem mercado
                    -- e sem informacao. Sao 349 companhias somando as tres instrucoes.
                    WHEN upper(MOTIVO_CANCEL) LIKE '%OFICIO%'
                      OR upper(MOTIVO_CANCEL) LIKE '%OF_CIO%'    THEN 'cancelamento_de_oficio'
                    ELSE 'cancelada_outro'
                END                AS destino,
                _downloaded_at     AS _as_of
            FROM ranqueado
            WHERE rn = 1
            """,
            [snap],
        )

        # ---------------- master_ticker ----------------
        tipos_sql = ", ".join("?" for _ in TIPOS_ACAO)
        # As duas fontes complementares entram como tabela temporaria. `ponte_emissor_cnpj`
        # pode nao existir (ela e opcional, vem de uma consulta a API da B3), e nesse caso
        # o vinculo por essa via simplesmente nao acontece -- nunca vira erro.
        con.register("_crosswalk", _crosswalk_identidade())
        if not warehouse.table_exists(con, "ponte_emissor_cnpj"):
            con.execute("CREATE TEMP TABLE ponte_emissor_cnpj (emissor VARCHAR, cnpj VARCHAR)")
        con.execute("DROP TABLE IF EXISTS master_ticker")
        con.execute(
            f"""
            CREATE TABLE master_ticker AS
            WITH fca AS (
                SELECT
                    upper(trim(Codigo_Negociacao)) AS ticker,
                    CNPJ_Companhia                 AS cnpj,
                    Valor_Mobiliario               AS tipo_papel,
                    ano_fca,
                    Nome_Empresarial               AS nome_na_epoca,
                    Segmento                       AS segmento,
                    Data_Inicio_Negociacao         AS inicio_negociacao_cvm,
                    Data_Fim_Negociacao            AS fim_negociacao_cvm
                FROM cvm_fca_valores
                WHERE Valor_Mobiliario IN ({tipos_sql})
                  AND Codigo_Negociacao IS NOT NULL
                  AND trim(Codigo_Negociacao) <> ''
            ),
            agg_fca AS (
                SELECT ticker, cnpj,
                       any_value(tipo_papel)           AS tipo_papel,
                       min(ano_fca)                    AS primeiro_ano_fca,
                       max(ano_fca)                    AS ultimo_ano_fca,
                       count(DISTINCT ano_fca)         AS anos_no_fca,
                       min(inicio_negociacao_cvm)      AS inicio_negociacao_cvm,
                       max(fim_negociacao_cvm)         AS fim_negociacao_cvm,
                       -- Nome como estava no FCA mais antigo e no mais recente: quando os
                       -- dois diferem, houve troca de razao social dentro do periodo.
                       arg_min(nome_na_epoca, ano_fca) AS nome_primeiro_ano,
                       arg_max(nome_na_epoca, ano_fca) AS nome_ultimo_ano,
                       arg_max(segmento, ano_fca)      AS segmento
                FROM fca
                GROUP BY ticker, cnpj
            ),
            pregao AS (
                SELECT ticker,
                       min(data)::DATE      AS primeiro_pregao,
                       max(data)::DATE      AS ultimo_pregao,
                       count(*)             AS n_pregoes,
                       any_value(isin)      AS isin,
                       count(DISTINCT isin) AS n_isins,
                       -- Segunda ponte de identidade, independente do FCA.
                       -- O ISIN brasileiro tem a forma BR + <4 chars do emissor> + ACN...
                       -- Todas as classes de uma mesma empresa compartilham esse trecho
                       -- (BRCSNAACNOR6 -> CSNA), entao ele agrupa ON/PN/Unit da mesma
                       -- companhia sem depender do Codigo_Negociacao do FCA -- que esta
                       -- vazio em metade das linhas e as vezes traz lixo ("4030", "NAO HA").
                       -- ATENCAO: o emissor do ISIN NAO sobrevive a troca de razao social
                       -- (TRPL -> ISAE), entao ele identifica PAPEL, nunca EMPRESA no tempo.
                       any_value(substr(isin, 3, 4)) AS emissor_isin
                FROM b3_cotahist
                -- Mesmo universo do painel: lote padrao MAIS os regimes especiais.
                -- Filtrar so '02' aqui repetiria o erro que a Etapa 2 corrigiu -- a
                -- empresa em recuperacao judicial sumiria da identidade tambem.
                WHERE codbdi IN ('02','05','06','07','08','09','11','58')
                GROUP BY ticker
            )
            ,
            -- PONTE 2: ISIN -> emissor -> codeCVM (API da B3) -> CNPJ, com guarda de nome.
            ponte_b3 AS (
                SELECT emissor, any_value(cnpj) AS cnpj FROM ponte_emissor_cnpj GROUP BY 1
            ),
            -- PONTE 3: irmao de emissor. Todas as classes de uma empresa compartilham os
            -- 4 chars de emissor do ISIN (BRCSNAACNOR6 -> CSNA). Se QUALQUER classe tem
            -- CNPJ pelo FCA, as irmas herdam -- CSNA3 resolve CSNA4 sem inventar nada.
            -- Vale so DENTRO do periodo: o emissor nao sobrevive a troca de razao social
            -- (TRPL -> ISAE), entao ele identifica papel, nunca empresa no tempo.
            irmaos AS (
                SELECT pr.emissor_isin AS emissor, any_value(a.cnpj) AS cnpj
                FROM pregao pr JOIN agg_fca a ON a.ticker = pr.ticker
                WHERE a.cnpj IS NOT NULL
                GROUP BY 1
            ),
            -- PONTE 4: decisao humana, versionada em crosswalk/identidade.csv
            crosswalk AS (SELECT ticker, cnpj FROM _crosswalk)
            SELECT COALESCE(a.ticker, p.ticker) AS ticker,
                   -- PRIORIDADE DECLARADA. A ordem nao e arbitraria: cai da fonte oficial
                   -- e datada para a inferida, e por ultimo para a decidida a mao. Cada
                   -- linha registra de onde veio, entao da para auditar por fonte e
                   -- rebaixar uma delas depois sem refazer o resto.
                   COALESCE(a.cnpj, pb.cnpj, ir.cnpj, cw.cnpj) AS cnpj,
                   CASE WHEN a.cnpj  IS NOT NULL THEN 'fca'
                        WHEN pb.cnpj IS NOT NULL THEN 'ponte_b3_isin'
                        WHEN ir.cnpj IS NOT NULL THEN 'irmao_mesmo_emissor'
                        WHEN cw.cnpj IS NOT NULL THEN 'crosswalk_manual'
                        ELSE NULL END AS fonte_do_vinculo,
                   a.tipo_papel, a.segmento,
                   a.nome_primeiro_ano, a.nome_ultimo_ano,
                   a.primeiro_ano_fca, a.ultimo_ano_fca, a.anos_no_fca,
                   a.inicio_negociacao_cvm, a.fim_negociacao_cvm,
                   p.primeiro_pregao, p.ultimo_pregao, p.n_pregoes,
                   p.isin, p.n_isins, p.emissor_isin,
                   -- Classificacao do papel pelo sufixo do ticker. BDR e ETF nao sao
                   -- companhia aberta brasileira e por isso nunca terao FCA: separar os
                   -- dois evita contar como "falha de vinculo" o que e escopo diferente.
                   CASE WHEN regexp_matches(COALESCE(a.ticker, p.ticker), '(33|34|35|39)$') THEN 'bdr'
                        WHEN regexp_matches(COALESCE(a.ticker, p.ticker), '11$')            THEN 'unit_etf_fii'
                        WHEN regexp_matches(COALESCE(a.ticker, p.ticker), '[0-9]B$')        THEN 'nao_padrao'
                        WHEN regexp_matches(COALESCE(a.ticker, p.ticker), '[1-8]$')         THEN 'acao'
                        ELSE 'outro' END AS classe_papel,
                   CASE WHEN COALESCE(a.cnpj, pb.cnpj, ir.cnpj, cw.cnpj) IS NULL
                             THEN 'sem_vinculo_cvm'
                        WHEN p.ticker IS NULL THEN 'sem_pregao_lote_padrao'
                        ELSE 'ok' END AS situacao_vinculo
            FROM agg_fca a
            FULL OUTER JOIN pregao p ON p.ticker = a.ticker
            LEFT JOIN ponte_b3  pb ON pb.emissor = p.emissor_isin
            LEFT JOIN irmaos    ir ON ir.emissor = p.emissor_isin
            LEFT JOIN crosswalk cw ON cw.ticker  = COALESCE(a.ticker, p.ticker)
            """,
            list(TIPOS_ACAO),
        )

        # ---------------- master_sucessao ----------------
        con.execute("DROP TABLE IF EXISTS master_sucessao")
        con.execute(
            """
            CREATE TABLE master_sucessao AS
            WITH multi AS (
                SELECT cnpj
                FROM master_ticker
                WHERE cnpj IS NOT NULL
                GROUP BY cnpj
                HAVING count(DISTINCT ticker) > 1
            )
            SELECT t.cnpj, e.nome_atual, t.ticker, t.tipo_papel,
                   t.nome_primeiro_ano, t.nome_ultimo_ano,
                   t.primeiro_ano_fca, t.ultimo_ano_fca,
                   t.primeiro_pregao, t.ultimo_pregao, t.n_pregoes,
                   e.destino
            FROM master_ticker t
            JOIN multi m USING (cnpj)
            LEFT JOIN master_empresa e USING (cnpj)
            ORDER BY t.cnpj, t.primeiro_ano_fca, t.ticker
            """
        )

        return {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("master_empresa", "master_ticker", "master_sucessao")
        }


if __name__ == "__main__":
    for tabela, n in construir().items():
        print(f"{tabela:<20} {n:>7,} linhas")
