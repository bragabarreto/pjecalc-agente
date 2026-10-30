"""Horário de Brasília para exibição.

O banco guarda datetimes naive em UTC (`datetime.utcnow()`). Brasília é UTC−3 fixo
(sem horário de verão desde 2019) — mesmo critério do gerador de PJC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))


def brt(dt: datetime | None, formato: str = "%d/%m/%Y %H:%M:%S") -> str:
    """Naive UTC (ou aware) -> texto em Brasília; None -> '—'."""
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime(formato)
