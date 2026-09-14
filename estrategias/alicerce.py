"""Roda o alicerce inteiro de uma vez: o null certo e as tres familias.

POR QUE ISTO EXISTE. Ate 11/09/2026 a barra do projeto era produzida por script ad hoc,
refeito de memoria a cada rodada. Isso sobreviveu enquanto o numero nao mudava; quando ele
mudou tres vezes em dois dias -- 0,57, depois 0,33, depois 0,06 -- ficou claro que o
problema nao era o numero, era nao haver um comando unico que o reproduza.

    python -m estrategias.alicerce            # a barra oficial, grava no ledger
    python -m estrategias.alicerce --seco     # mesma coisa, sem gravar trial
    python -m estrategias.alicerce --momento  # a grade de robustez do momento

O que sai daqui vai para o EQUIPE.md, que e o que o Codex le. Se os dois discordarem, o
errado e o EQUIPE.md.
"""
from __future__ import annotations

import dataclasses as dc
import sys

from estrategias import motor, sinais


def familias() -> dict:
    """Os tres sinais do alicerce. Cada um e uma funcao pura sobre `emissor_mensal`."""
    return {
        "momento 12-1": sinais.momento,
        "reversao 1 mes": sinais.reversao,
        "armagedom defensivo": sinais.defensivo_armagedom,
    }


def rodar_tudo(par: motor.Parametros | None = None, *, registrar: bool = True) -> dict:
    par = par or motor.Parametros()
    resultados = {"BENCHMARK equal-weight": motor.benchmark(par)}
    for nome, construir in familias().items():
        resultados[nome] = motor.rodar(construir(), par, nome=nome, registrar=registrar)
    return resultados


def tabela(resultados: dict) -> str:
    """Uma linha por estrategia, com o que o protocolo de leitura exige junto."""
    cab = (f"{'':24s} {'liquido':>9s} {'s/ CDI':>8s} {'sharpe':>7s} {'maxDD':>8s}"
           f" {'giro':>6s} {'custo':>7s} {'quebra':>7s} {'capacidade':>12s}")
    linhas = [cab, "-" * len(cab)]
    for nome, r in resultados.items():
        if "erro" in r:
            linhas.append(f"{nome:24s} {r['erro']}")
            continue
        l = r["liquido"]
        linhas.append(
            f"{nome:24s} {l.get('retorno_anual', float('nan')):+8.1%}"
            f" {l.get('retorno_sobre_cdi', float('nan')):+8.1%}"
            f" {l.get('sharpe', float('nan')):7.2f}"
            f" {l.get('max_drawdown', float('nan')):8.1%}"
            f" {r['giro_medio']:6.0%} {r['custo_anual']:7.1%}"
            f" {str(r['custo_que_quebra']) + 'x':>7s}"
            f" {'R$ ' + format(r['capacidade_mediana'] / 1e6, '.1f') + ' mi':>12s}")
    return "\n".join(linhas)


def grade_momento(par: motor.Parametros | None = None, *,
                  registrar: bool = True) -> list[dict]:
    """As 24 variacoes: formacao 3/6/9/12 x pulo 0/1 x 10/20/40 papeis.

    A grade existe para responder uma pergunta so, e ela e desconfortavel: o ponto que a
    literatura manda usar (12-1, 20 papeis) e um achado ou e um sorteio? Medida em
    11/09/2026 na base contaminada, a mediana das 24 PERDIA do benchmark. Escolher o
    melhor de 24 e chamar de resultado seria construir o numero em vez de medi-lo.
    """
    par = par or motor.Parametros()
    painel = motor._painel(par)
    saida = []
    for formacao in (3, 6, 9, 12):
        for pulo in (0, 1):
            sinal = sinais.momento(formacao=formacao, pulo=pulo)
            for n in (10, 20, 40):
                nome = f"momento {formacao}-{pulo} x {n} papeis"
                r = motor.rodar(sinal, dc.replace(par, n_papeis=n), nome=nome,
                                registrar=registrar, painel=painel)
                if "erro" in r:
                    continue
                saida.append({"variacao": nome, **{k: r["liquido"].get(k) for k in
                                                   ("retorno_anual", "retorno_sobre_cdi",
                                                    "sharpe", "max_drawdown")},
                              "giro_medio": r["giro_medio"],
                              "custo_anual": r["custo_anual"],
                              "capacidade": r["capacidade_mediana"]})
    return saida


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    seco = "--seco" in argv
    if "--momento" in argv:
        import pandas as pd
        g = pd.DataFrame(grade_momento(registrar=not seco)).sort_values("sharpe")
        print(g.to_string(index=False))
        print()
        print(f"sharpe: min {g['sharpe'].min():.3f}"
              f"  mediana {g['sharpe'].median():.3f}"
              f"  max {g['sharpe'].max():.3f}  (n = {len(g)})")
        return
    resultados = rodar_tudo(registrar=not seco)
    print(tabela(resultados))
    print()
    for r in resultados.values():
        if "erro" not in r:
            print(motor.relatorio(r), "\n")


if __name__ == "__main__":
    main()
