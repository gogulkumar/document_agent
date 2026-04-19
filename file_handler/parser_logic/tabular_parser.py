"""CSV/TSV parser using pandas."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        import pandas as pd  # type: ignore
        sep = "\t" if file_path.endswith(".tsv") else ","
        df = pd.read_csv(file_path, sep=sep, encoding="utf-8", on_bad_lines="skip")
        return df.to_markdown(index=False)
    except Exception as e:
        return f"[CSV PARSE ERROR: {e}]"
