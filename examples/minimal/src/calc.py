"""A tiny module so the example has something real to test."""


def add(left: float, right: float) -> float:
    return left + right


def divide(left: float, right: float) -> float:
    if right == 0:
        raise ValueError("division by zero")
    return left / right
