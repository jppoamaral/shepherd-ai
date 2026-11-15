"""Small wording helpers shared by the services that write plain-language text."""

from datetime import date


def long_day(d: date) -> str:
    """Sun Oct 11"""
    return f"{d:%a} {d:%b} {d.day}"


def short_day(d: date) -> str:
    """Oct 11"""
    return f"{d:%b} {d.day}"


def count_of(n: int, one: str, many: str) -> str:
    """One helper / 3 helpers"""
    return f"{'One' if n == 1 else n} {one if n == 1 else many}"


def and_list(items: list[str]) -> str:
    """Anna, Emily and Rachel"""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
