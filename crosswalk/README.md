# Crosswalk — decisões humanas de identidade e sucessão

Regra 6 do projeto: **auditoria mede, não conserta.** Correção é decisão humana e vira
arquivo versionado. Estes CSVs entram no git; cada linha carrega a evidência que a
sustenta e a data em que foi decidida.

O código **nunca escreve aqui**. Ele só lê, e emite para `crosswalk/pendentes_*.csv` a
lista do que não conseguiu resolver sozinho.

## `identidade.csv` — ticker → CNPJ

Para o resíduo que nenhuma fonte automática resolve. O buraco é estrutural e conhecido:
o campo `Codigo_Negociacao` do FCA da CVM está **vazio de 2010 a 2017** — a CVM só passou
a preenchê-lo em 2018. Logo não existe ponte oficial ticker↔CNPJ antes disso, e quem
morreu antes de 2018 fica de fora. Medido em 10/09/2026: dos 461 papéis que morreram antes
de 2018, só 65,9% tinham CNPJ.

| coluna | conteúdo |
|---|---|
| `ticker` | o papel, como aparece no COTAHIST |
| `cnpj` | no formato da CVM, com pontuação: `00.000.000/0001-91` |
| `evidencia` | **onde você viu**. Ex.: "FCA 2019 da sucessora lista o ticker antigo", "prospecto de OPA na CVM", "fato relevante de 12/03/2014". Sem isso a linha não vale |
| `decidido_em` | AAAA-MM-DD |
| `decidido_por` | quem decidiu |

Nunca preencher por semelhança de nome. `KLABIN S/A` casa com três empresas na base da
CVM, duas delas canceladas — foi exatamente esse tipo de casamento por nome que deixou a
ABEV3 com zero dividendos por treze anos.

## `sucessao.csv` — quando o CNPJ muda

Incorporação e fusão trocam a companhia, não só o ticker. Aí nem o CNPJ liga as pontas, e
só documento resolve.
