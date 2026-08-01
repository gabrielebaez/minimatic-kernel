"""Regression coverage for examples/tour.md: if a future change breaks the
demo, this should fail loudly rather than being noticed only by a human
running it manually.

Indices below were derived from an actual run of the file (each SetDelayed
statement also produces a result — the defined head's Symbol — so they
count toward the position of the results that follow them)."""

from pathlib import Path

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol

TOUR_PATH = Path(__file__).parent.parent / "examples" / "tour.md"


def _list(*items):
    return Expression(Symbol("List"), *items)


def test_tour_runs_without_error_and_produces_expected_results(kernel):
    results = kernel.eval_file(str(TOUR_PATH))

    assert len(results) == 43

    # describe(5), describe("hi"), describe(3.14) — after 3 SetDelayed clauses
    assert results[3] == "an integer"
    assert results[4] == "a string"
    assert results[5] == "something else"

    # fact(10) — after 2 SetDelayed clauses
    assert results[8] == 3628800

    # fib(10) — after 3 SetDelayed clauses
    assert results[12] == 55

    # fizzbuzz map — after 4 classify clauses + 1 fizzbuzz clause
    assert results[18] == _list(
        1, 2, "Fizz", 4, "Buzz", "Fizz", 7, 8, "Fizz", "Buzz", 11, "Fizz", 13, 14, "FizzBuzz",
    )

    # sum_all(1..5) — after 1 SetDelayed clause
    assert results[20] == 15

    # Listable +, Listable ^ (direct), Listable ^ (via /.)
    assert results[21] == _list(11, 22, 33, 44)
    assert results[22] == _list(1, 4, 9, 16)
    assert results[23] == _list(1, 4, 9, 16)

    # /. with a rule list
    assert results[24] == _list(1, 0, 2, -1, 3)

    # add5(10), add(5)(20) — after 1 SetDelayed clause + 1 Closure value
    assert results[27] == 15
    assert results[28] == 25

    # sum of squares via pipe/map/fold
    assert results[29] == 30

    # trailing list-op block: xs, length, head, tail, append
    assert results[30] == _list(10, 20, 30)
    assert results[31] == 3
    assert results[32] == 10
    assert results[33] == _list(20, 30)
    assert results[34] == _list(10, 20, 30, 40)

    # control-flow section: if, grade (switch-based), for, greet (CompoundExpression)
    assert results[35] == "yes"
    assert results[36] == Symbol("grade")
    assert results[37] == "A"
    assert results[38] == "C"
    assert results[39] == "F"
    assert results[40] is None  # for(0..5, y -> print(y))
    assert results[41] == Symbol("greet")
    assert results[42] is None  # greet() -> CompoundExpression's last stmt is print(...)
