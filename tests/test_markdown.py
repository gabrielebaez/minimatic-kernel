from minimatic.markdown import extract_minimatic_blocks


def test_extracts_tagged_blocks_only():
    text = """
# Title

Some prose.

```python
print("not minimatic")
```

```minimatic
x = 1
```

More prose.

```mmt
y = 2
```
"""
    blocks = extract_minimatic_blocks(text)
    assert blocks == ["x = 1", "y = 2"]


def test_bare_fences_are_ignored():
    text = """
```
double(x: _int) := 2 * x
```
"""
    assert extract_minimatic_blocks(text) == []


def test_no_blocks_returns_empty_list():
    assert extract_minimatic_blocks("just prose, no code") == []


def test_multiple_lines_preserved_within_a_block():
    text = """
```minimatic
[1, "N/A", 3, "N/A", 5]
|> map(x -> x /. "N/A" -> 0)
|> fold(plus, 0)
```
"""
    (block,) = extract_minimatic_blocks(text)
    assert block.splitlines() == [
        '[1, "N/A", 3, "N/A", 5]',
        '|> map(x -> x /. "N/A" -> 0)',
        "|> fold(plus, 0)",
    ]
