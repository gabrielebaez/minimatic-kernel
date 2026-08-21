import pytest

from minimatic.ast.symbol import clear_symbol_cache


@pytest.fixture(autouse=True)
def _reset_symbol_cache():
    """Keep symbol interning isolated between tests."""
    yield
    clear_symbol_cache()


@pytest.fixture
def kernel():
    from minimatic.kernel import Kernel

    return Kernel()


@pytest.fixture
def ctx(kernel):
    """An evaluation context, for the parts of the matcher that evaluate —
    `Condition` guards. Same shape `eval.py` builds per call."""
    from minimatic.eval import Ctx

    return Ctx(kernel.global_env, kernel.evaluator)
