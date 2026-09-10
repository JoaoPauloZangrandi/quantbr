"""Raio-x da base. Rode `python ver.py` para saber o que tem la dentro.

Serve para responder rapido tres perguntas: o que existe, ate quando vai, e onde estao os
buracos. Nao altera nada -- abre o warehouse em modo somente leitura.

Uso:
    python ver.py                 # panorama do painel de acoes
    python ver.py PETR4 VALE3     # historico de papeis especificos
    python ver.py --tudo          # inclui as tabelas fora do escopo atual
"""
from __future__ import annotations

import sys

import pandas as pd

import config
import warehouse

TABELA = "acoes_diario"


def _p(titulo: str) -> None:
    print("\n" + "=" * 78)
    print(titulo)
    print("=" * 78)


def panorama() -> None:
    with warehouse.connect(read_only=True) as con:
        _p("ONDE FICA")
        tam = config.DB_PATH.stat().st_size / 1e6 if config.DB_PATH.exists() else 0
        print(f"  arquivo : {config.DB_PATH}")
        print(f"  tamanho : {tam:,.0f} MB")
        print(f"  brutos  : {config.RAW}")

        _p(f"TABELA PRINCIPAL: {TABELA}")
        print(con.execute(f"DESCRIBE {TABELA}").df()[
            ["column_name", "column_type"]].to_string(index=False))

        _p("COBERTURA")
        print(con.execute(f"""
            SELECT count(*)                  AS linhas,
                   count(DISTINCT ticker)    AS papeis,
                   min(data)                 AS primeiro_pregao,
                   max(data)                 AS ultimo_pregao,
                   count(DISTINCT data)      AS pregoes
            FROM {TABELA}
        """).df().to_string(index=False))

        print("\npor classe:")
        print(con.execute(f"""
            SELECT classe, count(DISTINCT ticker) AS papeis, count(*) AS linhas
            FROM {TABELA} GROUP BY 1 ORDER BY linhas DESC
        """).df().to_string(index=False))

        _p("EVOLUCAO ANO A ANO")
        # `entraram` e `sairam` sao o retrato do survivorship: se `sairam` der zero em
        # algum ano, ou o dado esta incompleto ou o filtro esta errado.
        print(con.execute(f"""
            WITH vida AS (
                SELECT ticker, min(data) AS entrou, max(data) AS saiu
                FROM {TABELA} WHERE classe IN ('on','pn') GROUP BY ticker
            ),
            anos AS (SELECT DISTINCT year(data) AS ano FROM {TABELA})
            SELECT a.ano,
                   (SELECT count(DISTINCT ticker) FROM {TABELA} t
                     WHERE year(t.data)=a.ano AND t.classe IN ('on','pn'))      AS papeis,
                   (SELECT count(*) FROM vida v WHERE year(v.entrou)=a.ano)     AS entraram,
                   (SELECT count(*) FROM vida v WHERE year(v.saiu)=a.ano
                       AND v.saiu < (SELECT max(data)-30 FROM {TABELA}))        AS sairam
            FROM anos a ORDER BY a.ano
        """).df().to_string(index=False))

        _p("LIQUIDEZ HOJE (ultimo pregao, top 10 por volume)")
        print(con.execute(f"""
            SELECT ticker, empresa, fechamento, fechamento_ajustado,
                   round(volume/1e6, 1) AS volume_milhoes, negocios
            FROM {TABELA}
            WHERE data = (SELECT max(data) FROM {TABELA})
            ORDER BY volume DESC LIMIT 10
        """).df().to_string(index=False))

        _p("SANIDADE")
        s = con.execute(f"""
            SELECT count(*) FILTER (WHERE fechamento <= 0)                AS preco_nao_positivo,
                   count(*) FILTER (WHERE fechamento < 1)                 AS preco_abaixo_de_1_real,
                   count(*) FILTER (WHERE volume = 0)                     AS volume_zero,
                   count(*) FILTER (WHERE maxima < minima)                AS max_menor_que_min,
                   count(*) FILTER (WHERE fechamento > maxima
                                       OR fechamento < minima)            AS fechamento_fora_da_faixa
            FROM {TABELA}
        """).df()
        print(s.to_string(index=False))
        print("\n  preco abaixo de R$1 nao e erro: e papel de centavos, e existe mesmo.")
        print("  se as tres ultimas colunas nao forem zero, ha problema de dado.")

        _p("AS TRES SERIES DE PRECO")
        ev = con.execute(f"""
            SELECT count(*) FILTER (WHERE tem_evento)                 AS pregoes_com_evento,
                   count(DISTINCT ticker) FILTER (WHERE tem_evento)   AS papeis_com_evento,
                   count(*) FILTER (WHERE tem_provento)               AS pregoes_ex_provento,
                   count(DISTINCT ticker) FILTER (WHERE tem_provento) AS papeis_com_provento
            FROM {TABELA}
        """).df()
        print(ev.to_string(index=False))
        print("\n  fechamento               -> nominal. Ordem, corretagem, emolumento, lote.")
        print("  fechamento_ajustado      -> desdobramento e grupamento corrigidos.")
        print("  fechamento_retorno_total -> tambem com dividendo e JCP. E o do acionista.")

        cob = con.execute(f"""
            SELECT count(DISTINCT ticker) FILTER (WHERE tem_provento) AS com,
                   count(DISTINCT ticker) AS total
            FROM {TABELA}
        """).df().iloc[0]
        print(f"\n  cobertura de provento: {cob['com']:,} de {cob['total']:,} papeis "
              f"({100 * cob['com'] / cob['total']:.0f}%).")
        print("  Os que faltam sao, em boa parte, empresas que sairam da bolsa: a B3 nao")
        print("  mantem o historico de provento delas. Reportar essa cobertura junto de")
        print("  qualquer resultado que use a serie de retorno total.")

        _p("REGIME DE NEGOCIACAO")
        print(con.execute(f"""
            SELECT regime, count(DISTINCT ticker) AS papeis, count(*) AS pregoes
            FROM {TABELA} GROUP BY 1 ORDER BY pregoes DESC
        """).df().to_string(index=False))
        print()
        print("  'normal' e lote padrao. O resto e empresa em recuperacao, reorganizacao")
        print("  ou leilao -- e ela CONTINUA na base. Filtrar so o lote padrao apagava o")
        print("  papel exatamente quando a empresa quebrava, que e o momento que mais")
        print("  importa para um teste sem survivorship.")

        _p("SAIDA DO PAPEL")
        print(con.execute(f"""
            SELECT motivo_saida, count(*) AS papeis,
                   count(retorno_delisting) AS com_retorno_de_delisting
            FROM {TABELA} WHERE motivo_saida IS NOT NULL
            GROUP BY 1 ORDER BY papeis DESC
        """).df().to_string(index=False))
        print()
        print("  'sucessao_de_ticker' NAO e delisting: EMBR3 virou EMBJ3 e a posicao")
        print("  continua. Onde ha retorno de delisting ele vale -100% e e CONVENCAO,")
        print("  nao medida -- por isso `delisting_observado` fica FALSE.")

        _p("RETORNO (a primitiva)")
        print(con.execute(f"""
            SELECT count(retorno_qtd)                  AS com_retorno,
                   round(avg(retorno_qtd) * 100, 4)    AS media_pct_dia,
                   round(stddev(retorno_qtd) * 100, 2) AS desvio_pct_dia,
                   round(min(retorno_qtd), 3)          AS minimo,
                   round(max(retorno_qtd), 1)          AS maximo
            FROM {TABELA} WHERE classe IN ('on','pn')
        """).df().to_string(index=False))
        print()
        print("  retorno_qtd e retorno_total sao o dado primario; preco ajustado e")
        print("  derivado deles. O retorno de um dia depende so daquele dia e do")
        print("  anterior, entao evento novo nao reescreve o passado.")
        print("  Maximo muito alto = grupamento nao detectado, quase sempre papel de")
        print("  centavos em recuperacao judicial. Sao conhecidos e declarados.")

        _p("VALOR DE MERCADO")
        print(con.execute(f"""
            SELECT CASE WHEN data < '2011-07-01' THEN 'antes de jul/2011'
                        ELSE 'de jul/2011 em diante' END AS periodo,
                   count(*) AS linhas,
                   count(*) FILTER (WHERE valor_mercado_empresa IS NOT NULL) AS com_valor,
                   round(100.0 * count(*) FILTER (WHERE valor_mercado_empresa IS NOT NULL)
                         / count(*), 1) AS pct
            FROM {TABELA} WHERE classe IN ('on','pn')
            GROUP BY 1 ORDER BY 1
        """).df().to_string(index=False))
        print("\n  A quantidade de acoes vem do Formulario de Referencia da CVM, que so")
        print("  comeca em 2010 -- por isso quase nao ha valor de mercado antes de 2011.")
        print("  Aplicado com 6 meses de defasagem: o documento de 31/12 so e entregue")
        print("  por volta de maio seguinte, e usar antes disso seria look-ahead.")

        print("\n  As maiores hoje:")
        print(con.execute(f"""
            SELECT ticker, empresa, round(valor_mercado_empresa/1e9, 1) AS valor_bilhoes
            FROM {TABELA}
            WHERE data = (SELECT max(data) FROM {TABELA})
              AND valor_mercado_empresa IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY cnpj ORDER BY volume DESC) = 1
            ORDER BY valor_mercado_empresa DESC LIMIT 8
        """).df().to_string(index=False))


def historico(tickers: list[str]) -> None:
    with warehouse.connect(read_only=True) as con:
        marcas = ", ".join("?" for _ in tickers)
        _p(f"HISTORICO: {', '.join(tickers)}")
        print(con.execute(f"""
            SELECT ticker, any_value(empresa) AS empresa, count(*) AS pregoes,
                   min(data) AS primeiro, max(data) AS ultimo,
                   round(min(fechamento), 2) AS menor_preco,
                   round(max(fechamento), 2) AS maior_preco,
                   round(median(volume)/1e6, 1) AS volume_mediano_mi
            FROM {TABELA} WHERE ticker IN ({marcas})
            GROUP BY ticker ORDER BY ticker
        """, tickers).df().to_string(index=False))

        print("\nultimos 5 pregoes:")
        print(con.execute(f"""
            SELECT ticker, data, fechamento, round(volume/1e6,1) AS vol_mi
            FROM (SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY data DESC) rn
                  FROM {TABELA} WHERE ticker IN ({marcas}))
            WHERE rn <= 5 ORDER BY ticker, data
        """, tickers).df().to_string(index=False))


def tudo() -> None:
    with warehouse.connect(read_only=True) as con:
        _p("TODAS AS TABELAS DO WAREHOUSE")
        linhas = []
        for (t,) in con.execute(
                "SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall():
            n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            linhas.append({"tabela": t, "linhas": n,
                           "no_escopo_atual": "sim" if t == TABELA else "nao"})
        print(pd.DataFrame(linhas).to_string(index=False))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    args = [a for a in sys.argv[1:]]
    if "--tudo" in args:
        panorama()
        tudo()
    elif args:
        historico([a.upper() for a in args])
    else:
        panorama()
