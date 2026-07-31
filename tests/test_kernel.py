from minimatic.parser import parse_all


def test_parse_all_splits_independent_statements():
    stmts = parse_all("x = 1\ny = 2\nx + y")
    assert len(stmts) == 3


def test_parse_all_keeps_multiline_expression_as_one_statement():
    source = '[1, "N/A", 3, "N/A", 5]\n|> map(x -> x /. "N/A" -> 0)\n|> fold(plus, 0)'
    stmts = parse_all(source)
    assert len(stmts) == 1


def test_parse_all_empty_source():
    assert parse_all("   \n  ") == []


def test_kernel_run_evaluates_statements_in_order_against_shared_env(kernel):
    from minimatic.ast.symbol import Symbol

    results = kernel.run("x = 5\ndouble(y: _int) := y * 2\ndouble(x)")
    assert results[0] == 5
    assert results[1] == Symbol("double")  # SetDelayed returns the defined head
    assert results[2] == 10


def test_kernel_run_basic(kernel):
    results = kernel.run("x = 5\nx + 1")
    assert results[0] == 5
    assert results[1] == 6


def test_eval_file_plain_source(kernel, tmp_path):
    script = tmp_path / "script.mmt"
    script.write_text("x = 5\nx + 1\n")
    results = kernel.eval_file(str(script))
    assert results[-2:] == [5, 6]


def test_eval_file_markdown_runs_tagged_blocks_in_order(kernel, tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        """
# A tiny doc

Some prose that should be ignored, including a decoy fence:

```python
this_is_not_minimatic = "ignored"
```

```minimatic
double(x: _int) := 2 * x
```

More prose in between blocks.

```minimatic
double(21)
```
"""
    )
    results = kernel.eval_file(str(doc))
    assert results[-1] == 42


def test_eval_file_markdown_flagship_pipeline(kernel, tmp_path):
    doc = tmp_path / "flagship.md"
    doc.write_text(
        """
```minimatic
[1, "N/A", 3, "N/A", 5]
|> map(x -> x /. "N/A" -> 0)
|> fold(plus, 0)
```
"""
    )
    results = kernel.eval_file(str(doc))
    assert results == [9]


def test_eval_file_markdown_later_block_sees_earlier_bindings(kernel, tmp_path):
    doc = tmp_path / "shared_env.md"
    doc.write_text(
        """
```minimatic
x = 10
```

```minimatic
x + 5
```
"""
    )
    results = kernel.eval_file(str(doc))
    assert results == [10, 15]
