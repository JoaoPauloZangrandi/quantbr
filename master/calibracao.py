"""Calibracao do detector de eventos contra o gabarito da B3.

A pergunta que este modulo responde nao e "o detector parece bom?", e sim: de cada 100
eventos reais, quantos ele acha, e de cada 100 que ele aponta, quantos existem de fato.
Sem esses dois numeros, aplicar o detector nas empresas mortas -- onde nao ha gabarito --
seria fe, nao metodo.

Cuidados que mudam o resultado se forem ignorados:

1. CONVENCAO DE DATA. A B3 informa `lastDatePrior`, o ultimo pregao COM direito. O preco
   so cai no pregao SEGUINTE. Entao o gabarito da B3 casa com `data_ant` da deteccao, nao
   com `data`. Errar isso desloca tudo em um dia e zera o acerto.

2. FATOR VERSUS PERCENTUAL -- E A CONVENCAO MUDA POR TIPO DE EVENTO. Este detalhe ja
   invalidou uma rodada inteira de calibracao, entao vale escrever por extenso:

     DESDOBRAMENTO e BONIFICACAO -> percentual de acoes NOVAS por acao existente.
        PETR, 25/04/2008, percentual 100      => fator 2,0   (2:1)
        ALPA, 24/02/2010, percentual 1.900    => fator 20,0
        conversao: fator = 1 + percentual/100

     GRUPAMENTO -> o percentual JA E a razao, nao e percentual de coisa nenhuma.
        PETR, 21/06/2000, percentual 0,01     => fator 0,01  (100:1)
        GGBR, 30/04/2003, percentual 0,001    => fator 0,001 (1000:1)
        conversao: fator = percentual

   Aplicar 1 + p/100 no grupamento transforma 0,01 em 1,0001, e os 294 grupamentos do
   gabarito passam a nao casar com nada. Foi exatamente o que aconteceu na primeira
   medicao, e o sintoma foi erro mediano de fator de 8,3%.

3. NEM TODO EVENTO DA B3 E UM EVENTO DE RAZAO. CIS RED CAP (cisao com reducao de
   capital), INCORPORACAO, RESG TOTAL RV e REST CAP ACOES mudam o preco sem que exista
   um fator limpo de multiplicacao de acoes. Cobrar do detector que os encontre e cobrar
   o que ele nao promete: eles ficam FORA do denominador do recall e sao reportados a
   parte.

3. DENOMINADOR DA PRECISAO. So conta como falso positivo a deteccao num emissor em que a
   B3 RESPONDEU. Onde ela nao tem dado (empresa que saiu da bolsa), ausencia de registro
   nao e prova de que o evento nao houve -- e exatamente o buraco que o detector existe
   para cobrir. Misturar os dois casos faria a precisao parecer pessima por um motivo
   errado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse

# Folga de dias uteis entre a data da B3 e a data detectada. Deveria ser 0 pela convencao
# acima, mas feriado, suspensao de negociacao e papel iliquido criam defasagem legitima.
TOLERANCIA_DIAS = 5

# Eventos com fator de multiplicacao de acoes bem definido. Sao os unicos que o
# detector de razao pode, em principio, encontrar. Cisao e incorporacao mexem no preco
# sem razao limpa e ficam fora do denominador.
TIPOS_COM_RAZAO = ("DESDOBRAMENTO", "GRUPAMENTO", "BONIFICACAO")

# O detector so olha saltos de preco a partir de 30%. Bonificacao de 3% da razao 1,03 e
# e invisivel POR DESENHO, nao por falha. Cobrar recall sobre evento que ele nunca
# prometeu ver produz um numero pessimista e sem significado, entao o recall e medido
# duas vezes: sobre tudo, e sobre o que esta ao alcance.
RAZAO_MINIMA_DETECTAVEL = 1.30

# Emissor cujo gabarito tem pouquissimo evento nao serve para medir PRECISAO: quando a
# B3 nao tem a historia da empresa, uma deteccao sem par no gabarito nao e prova de erro.
# Medido: 351 dos 613 emissores que responderam 'ok' tem ZERO evento de quantidade, o que
# nao e cri­vel para empresas com anos de pregao. A precisao so e calculada onde ha
# evidencia de que a B3 realmente guarda o historico daquele emissor.
MINIMO_EVENTOS_PARA_AUDITAR = 3


def _preparar(con) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gabarito = con.execute("""
        SELECT emissor, isin, tipo,
               try_strptime(ultima_data_com, '%d/%m/%Y')::DATE AS data_com,
               TRY_CAST(replace(percentual, ',', '.') AS DOUBLE)  AS percentual
        FROM b3_eventos_quantidade
        WHERE _snapshot = (SELECT max(_snapshot) FROM b3_eventos_quantidade)
    """).df()
    gabarito = gabarito.dropna(subset=["data_com", "isin"])
    # percentual -> fator multiplicativo, com a convencao que muda por tipo (ver docstring)
    gabarito["fator_b3"] = np.where(
        gabarito["tipo"].str.upper() == "GRUPAMENTO",
        gabarito["percentual"],
        1.0 + gabarito["percentual"].fillna(0) / 100.0,
    )
    gabarito["tem_razao_limpa"] = gabarito["tipo"].str.upper().isin(TIPOS_COM_RAZAO)

    detectado = con.execute("""
        SELECT ticker, isin, data::DATE AS data_ex, data_ant::DATE AS data_com,
               fator_sugerido, confianca, fech_ant
        FROM eventos_detectados
        WHERE confianca IN ('alta', 'media', 'baixa')
    """).df()

    cobertura = con.execute("""
        SELECT emissor, resposta, n_quantidade
        FROM b3_eventos_cobertura
        WHERE _snapshot = (SELECT max(_snapshot) FROM b3_eventos_cobertura)
    """).df()
    return gabarito, detectado, cobertura


def _casar(gabarito: pd.DataFrame, detectado: pd.DataFrame) -> pd.DataFrame:
    """Casa gabarito e deteccao por ISIN + data proxima."""
    if gabarito.empty or detectado.empty:
        return pd.DataFrame()
    j = gabarito.merge(detectado, on="isin", how="left", suffixes=("_b3", "_det"))
    j["dias"] = (j["data_com_det"] - j["data_com_b3"]).dt.days.abs()
    j["casou"] = j["dias"] <= TOLERANCIA_DIAS
    # Para cada evento do gabarito, fica a deteccao mais proxima no tempo.
    j = j.sort_values(["isin", "data_com_b3", "dias"])
    return j.groupby(["isin", "data_com_b3"], as_index=False).first()


def relatorio() -> None:
    pd.set_option("display.width", 200)
    with warehouse.connect(read_only=True) as con:
        gabarito, detectado, cobertura = _preparar(con)

    ok = set(cobertura.loc[cobertura["resposta"] == "ok", "emissor"])
    print("=" * 74)
    print("COBERTURA DO GABARITO")
    print("=" * 74)
    print(cobertura["resposta"].value_counts().to_string())
    print(f"\nemissores com resposta util: {len(ok):,} de {len(cobertura):,}")
    print(f"eventos de quantidade no gabarito: {len(gabarito):,}")

    # Restringe o gabarito ao periodo que o nosso COTAHIST cobre.
    with warehouse.connect(read_only=True) as con:
        ini, fim = con.execute("SELECT min(data)::DATE, max(data)::DATE FROM b3_cotahist").fetchone()
    no_periodo = gabarito[(gabarito["data_com"] >= pd.Timestamp(ini))
                          & (gabarito["data_com"] <= pd.Timestamp(fim))]
    print(f"...dentro do periodo do COTAHIST ({ini} a {fim}): {len(no_periodo):,}")
    fora = no_periodo[~no_periodo["tem_razao_limpa"]]
    no_periodo = no_periodo[no_periodo["tem_razao_limpa"]]
    print(f"...destes, com fator de razao bem definido: {len(no_periodo):,}")
    if not fora.empty:
        print(f"   (fora do denominador, sem razao limpa: {len(fora):,} -> "
              f"{', '.join(sorted(fora['tipo'].unique()))})")

    casado = _casar(no_periodo, detectado)
    if casado.empty:
        print("\nnada a casar")
        return

    print("\n" + "=" * 74)
    print("RECALL -- dos eventos reais, quantos o detector acha")
    print("=" * 74)
    achou = casado["casou"].fillna(False)
    casado = casado.assign(_achou=achou)
    grande = ((casado["fator_b3"] >= RAZAO_MINIMA_DETECTAVEL)
              | (casado["fator_b3"] <= 1 / RAZAO_MINIMA_DETECTAVEL))
    print(f"eventos do gabarito no periodo : {len(casado):,}")
    print(f"detectados (qualquer confianca): {achou.sum():,}  ({100*achou.mean():.1f}%)")
    print()
    print(f"AO ALCANCE do detector (fator fora da faixa {1/RAZAO_MINIMA_DETECTAVEL:.2f}-"
          f"{RAZAO_MINIMA_DETECTAVEL:.2f}): {grande.sum():,}")
    if grande.any():
        print(f"   destes, detectados: {(achou & grande).sum():,}  "
              f"({100*achou[grande].mean():.1f}%)  <-- este e o recall que significa algo")
    fora_alcance = (~grande)
    if fora_alcance.any():
        print(f"pequenos demais para o detector ver: {fora_alcance.sum():,} "
              f"(bonificacao miuda; invisivel por desenho, nao por falha)")
    for nivel in ("alta", "media", "baixa"):
        n = ((casado["confianca"] == nivel) & achou & grande).sum()
        print(f"   dos ao alcance, {nivel:<6}: {n:,}")

    print("\nfator: o detector concorda com a B3 quando acha?")
    m = casado[achou].copy()
    if not m.empty:
        m["erro_fator"] = (m["fator_sugerido"] - m["fator_b3"]).abs() / m["fator_b3"]
        print(f"  erro mediano do fator: {m['erro_fator'].median():.4f}")
        print(f"  dentro de 2%: {100*(m['erro_fator'] <= 0.02).mean():.1f}%")

    print("\n" + "=" * 74)
    print("PRECISAO -- do que o detector aponta, quanto e real")
    print("=" * 74)
    det = detectado.copy()
    det["emissor"] = det["isin"].str.slice(2, 6)
    confiaveis = set(cobertura.loc[
        (cobertura["resposta"] == "ok")
        & (cobertura["n_quantidade"] >= MINIMO_EVENTOS_PARA_AUDITAR), "emissor"])
    print(f"emissores com historico crivel na B3 (>= {MINIMO_EVENTOS_PARA_AUDITAR} eventos): "
          f"{len(confiaveis):,} de {len(ok):,} que responderam")
    det_audit = det[det["emissor"].isin(confiaveis)]
    reais = set(zip(no_periodo["isin"], no_periodo["data_com"].dt.to_period("D")))

    def _e_real(r) -> bool:
        for delta in range(-TOLERANCIA_DIAS, TOLERANCIA_DIAS + 1):
            if (r["isin"], (r["data_com"] + pd.Timedelta(days=delta)).to_period("D")) in reais:
                return True
        return False

    if det_audit.empty:
        print("nenhuma deteccao em emissor com gabarito")
        return
    det_audit = det_audit.copy()
    det_audit["confirmado"] = det_audit.apply(_e_real, axis=1)
    resumo = (det_audit.groupby("confianca")["confirmado"]
              .agg(deteccoes="size", confirmadas="sum")
              .assign(precisao=lambda d: (100 * d["confirmadas"] / d["deteccoes"]).round(1)))
    print(resumo.to_string())
    print("\n(so emissores em que a B3 respondeu; onde ela nao tem dado, ausencia nao e prova)")


if __name__ == "__main__":
    relatorio()
