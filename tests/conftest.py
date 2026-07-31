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
