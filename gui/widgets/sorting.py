"""Ordinamento robusto e riutilizzabile per le tabelle della GUI.

Logica PURA (nessuna dipendenza da PyQt6): cosi' e' testabile senza
QApplication. Il :class:`DataclassTableModel` la usa per implementare il
sort a 3 stati sulle colonne.

Regole:
- i valori ``None`` vanno SEMPRE in fondo, sia in ordine crescente sia
  decrescente (non "vincono" mai l'ordinamento);
- tipi misti (numeri e stringhe) sono confrontati in modo robusto: i
  numeri vengono raggruppati prima delle stringhe, evitando ``TypeError``.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence


def sort_key(value: Any) -> tuple[int, Any]:
    """Chiave di ordinamento robusta per un valore non ``None``.

    Restituisce una tupla ``(categoria, valore_confrontabile)`` cosi' che
    numeri e stringhe non vengano mai confrontati direttamente tra loro.
    """
    # bool e' sottoclasse di int: normalizziamo a numero.
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    # Qualsiasi altro tipo: confronto per stringa case-insensitive.
    return (1, str(value).lower())


def sort_rows(
    rows: Sequence[Any],
    extractor: Callable[[Any], Any],
    descending: bool = False,
) -> list[Any]:
    """Ordina ``rows`` per il valore restituito da ``extractor``.

    ``None`` (o estrazioni fallite) finiscono sempre in coda, a prescindere
    dalla direzione. Tipi misti gestiti via :func:`sort_key`.
    """
    with_value: list[tuple[Any, Any]] = []
    none_rows: list[Any] = []
    for row in rows:
        try:
            value = extractor(row)
        except Exception:
            value = None
        if value is None:
            none_rows.append(row)
        else:
            with_value.append((row, value))
    with_value.sort(key=lambda pair: sort_key(pair[1]), reverse=descending)
    return [row for row, _ in with_value] + none_rows
