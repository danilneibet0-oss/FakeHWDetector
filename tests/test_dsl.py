import pytest

from fakehw.rules.dsl import ConditionError, evaluate, signal_names, validate


def test_basic_evaluation():
    assert evaluate("a == 1 and b in ['x', 'y']", {"a": 1, "b": "x"}) is True
    assert evaluate("not (a > 2)", {"a": 1}) is True
    assert evaluate("a or b", {"a": 0, "b": 0}) is False


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('x')",
        "a.__class__",
        "open('f')",
        "lambda: 1",
        "[x for x in y]",
        "a(1)",
        "a +",
        "",
    ],
)
def test_forbidden_or_invalid(expr):
    with pytest.raises(ConditionError):
        validate(expr)


def test_unknown_signal_is_error_at_eval():
    with pytest.raises(ConditionError):
        evaluate("a == 1", {})


def test_names_extracted():
    assert signal_names("a == 1 and (b or not c)") == {"a", "b", "c"}
