"""Deterministic validation of a small invoice CSV; never writes or imports data."""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_CHARS = 64_000
MAX_ERRORS = 20
HEADER = ["invoice_id", "amount", "invoice_date"]


def validate_csv(csv_text: str) -> dict[str, Any]:
    """Check ID uniqueness, finite decimal amounts and ISO calendar dates."""
    errors: list[dict[str, Any]] = []
    error_count = 0
    rows_read = 0

    def error(record: int, field: str, message: str) -> None:
        """Count every error while retaining at most MAX_ERRORS redacted details."""
        nonlocal error_count
        error_count += 1
        if len(errors) < MAX_ERRORS:
            errors.append({"record": record, "field": field, "message": message})

    if len(csv_text) > MAX_CHARS:
        error(0, "csv", f"input exceeds {MAX_CHARS} characters")
    else:
        reader = csv.reader(
            io.StringIO(csv_text.removeprefix("\ufeff"), newline=""), strict=True
        )
        seen: set[str] = set()
        try:
            if next(reader, None) != HEADER:
                error(
                    1, "header", "expected invoice_id,amount,invoice_date in that order"
                )
            else:
                for record, row in enumerate(reader, start=2):
                    if not row:
                        continue
                    rows_read += 1
                    if len(row) != 3:
                        error(record, "csv", "expected exactly three columns")
                        continue
                    invoice_id, amount, invoice_date = (value.strip() for value in row)
                    if not invoice_id:
                        error(record, "invoice_id", "required value is empty")
                    elif invoice_id in seen:
                        error(record, "invoice_id", "duplicate ID")
                    seen.add(invoice_id)
                    try:
                        if not Decimal(amount).is_finite():
                            raise InvalidOperation
                    except InvalidOperation:
                        error(record, "amount", "expected a finite decimal")
                    try:
                        if not re.fullmatch(
                            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", invoice_date
                        ):
                            raise ValueError
                        date.fromisoformat(invoice_date)
                    except ValueError:
                        error(
                            record, "invoice_date", "expected a valid YYYY-MM-DD date"
                        )
        except csv.Error:
            error(0, "csv", "malformed CSV quoting")

    return {
        "ok": error_count == 0,
        "rows_read": rows_read,
        "error_count": error_count,
        "errors": errors,
        "errors_truncated": error_count > len(errors),
    }
