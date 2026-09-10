"""Caminhos e constantes centrais do quantbr.

Regra do projeto: nenhum modulo inventa caminho proprio. Tudo sai daqui.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA = Path(os.environ.get("QUANTBR_DATA", ROOT / "data"))
RAW = DATA / "raw"           # arquivos originais baixados, nunca editados
WAREHOUSE = DATA / "warehouse"  # parquet tratado
DB_PATH = WAREHOUSE / "quantbr.duckdb"

# Ledger de trials (L1) fica separado do warehouse de dado de mercado de proposito:
# apagar/reconstruir o warehouse nao pode apagar o historico de tentativas.
PROTOCOL = ROOT / "protocol"
TRIALS_DB = PROTOCOL / "trials.duckdb"

# Decisoes humanas de identidade e sucessao. Regra 6 do projeto: auditoria mede, nao
# conserta -- correcao e decisao humana e vira ARQUIVO VERSIONADO, nao heuristica dentro
# do codigo. Estes CSVs entram no git e cada linha carrega a evidencia e a data.
CROSSWALK = ROOT / "crosswalk"

for _p in (RAW, WAREHOUSE, PROTOCOL, CROSSWALK):
    _p.mkdir(parents=True, exist_ok=True)

# Timezone de referencia do mercado
TZ = "America/Sao_Paulo"

USER_AGENT = "quantbr/0.1 (research; contato via github)"
