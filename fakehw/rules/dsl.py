"""Safe mini-DSL for rule conditions. Parsed with ast, walked against a whitelist; never eval()."""

import ast
import operator
from typing import Any

MAX_LENGTH = 500


class ConditionError(ValueError):
    pass


_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_ALLOWED = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.Compare, ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple,
    *tuple(_COMPARE),
)


def _parse(expr: str) -> ast.Expression:
    if not expr or not expr.strip():
        raise ConditionError("empty condition")
    if len(expr) > MAX_LENGTH:
        raise ConditionError("condition too long")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ConditionError(f"syntax error: {e.msg}") from e
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ConditionError(f"forbidden construct: {type(node).__name__}")
        if isinstance(node, ast.UnaryOp) and not isinstance(node.op, ast.Not):
            raise ConditionError("only 'not' is allowed as unary operator")
    return tree


def validate(expr: str) -> None:
    _parse(expr)


def signal_names(expr: str) -> set[str]:
    return {n.id for n in ast.walk(_parse(expr)) if isinstance(n, ast.Name)}


def evaluate(expr: str, signals: dict[str, Any]) -> bool:
    return bool(_eval(_parse(expr).body, signals))


def _eval(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ConditionError(f"unknown signal: {node.id}")
        return env[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, env) for e in node.elts]
    if isinstance(node, ast.UnaryOp):
        return not _eval(node.operand, env)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, env) for v in node.values)
        return any(_eval(v, env) for v in node.values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, env)
            try:
                if not _COMPARE[type(op)](left, right):
                    return False
            except TypeError as e:
                raise ConditionError(str(e)) from e
            left = right
        return True
    raise ConditionError(f"forbidden construct: {type(node).__name__}")
