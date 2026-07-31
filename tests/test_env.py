import pytest

from minimatic.env import Env
from minimatic.errors import UnboundSymbolError


def test_lookup_in_own_frame():
    env = Env({"x": 5})
    assert env.lookup("x") == 5


def test_lookup_falls_through_to_parent():
    parent = Env({"x": 5})
    child = parent.extend({"y": 10})
    assert child.lookup("x") == 5
    assert child.lookup("y") == 10


def test_child_shadows_parent():
    parent = Env({"x": 5})
    child = parent.extend({"x": 99})
    assert child.lookup("x") == 99
    assert parent.lookup("x") == 5


def test_unbound_raises():
    env = Env()
    with pytest.raises(UnboundSymbolError):
        env.lookup("nope")
    assert not env.has("nope")


def test_set_here_mutates_only_that_frame():
    parent = Env()
    child = parent.extend({})
    child.set_here("x", 1)
    assert child.lookup("x") == 1
    assert not parent.has("x")
