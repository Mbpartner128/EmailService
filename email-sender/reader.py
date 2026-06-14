# reader.py
import pandas as pd
import config


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to internal standard names."""
    rename = {}
    for col in df.columns:
        c = col.strip()
        if c == config.COL_NAME:
            rename[col] = "name"
        elif c == config.COL_EMAIL:
            rename[col] = "email"
        elif c == config.COL_STATUS:
            rename[col] = "status"
    return df.rename(columns=rename)


def _validate_columns(df: pd.DataFrame, sheet_name: str) -> None:
    columns = {str(col).strip() for col in df.columns}
    required = [config.COL_EMAIL]
    missing = [name for name in required if name not in columns]
    if missing:
        available = ", ".join(str(col).strip() for col in df.columns)
        raise ValueError(
            f"Sheet {sheet_name!r} is missing required column(s): "
            f"{', '.join(missing)}. Available columns: {available}"
        )


def load_clients(path: str = None) -> list[dict]:
    path = path or config.INPUT_FILE

    # Determine which sheets to read
    all_sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    target = config.TARGET_SHEETS

    if target is None:
        sheets_to_read = list(all_sheets.keys())
    elif isinstance(target, str):
        sheets_to_read = [target]
    else:
        sheets_to_read = list(target)

    clients = []
    for sheet_name in sheets_to_read:
        if sheet_name not in all_sheets:
            print(f"⚠️  Sheet not found: {sheet_name!r} — skipping")
            continue

        df = all_sheets[sheet_name].fillna("")
        _validate_columns(df, sheet_name)
        df = _normalize(df)

        for _, row in df.iterrows():
            name   = row.get("name",   "").strip()
            email  = row.get("email",  "").strip()
            status = row.get("status", "").strip()

            # Skip rows with no name and no email (blank rows)
            if not name and not email:
                continue

            clients.append({
                "name":   name,
                "email":  email,
                "status": status,
                "_sheet": sheet_name,
            })

    return clients
