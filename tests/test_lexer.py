from minimatic.lexer import TokenKind, tokenize


def kinds(source):
    return [t.kind for t in tokenize(source)]


def test_integers_and_floats():
    toks = tokenize("1 2.5 10")
    assert [t.kind for t in toks[:3]] == [TokenKind.INT, TokenKind.FLOAT, TokenKind.INT]
    assert toks[0].value == 1
    assert toks[1].value == 2.5
    assert toks[2].value == 10


def test_string_with_escapes():
    toks = tokenize(r'"hello \"world\"" ')
    assert toks[0].kind is TokenKind.STRING
    assert toks[0].value == 'hello "world"'


def test_booleans():
    toks = tokenize("True False")
    assert toks[0].kind is TokenKind.TRUE
    assert toks[0].value is True
    assert toks[1].kind is TokenKind.FALSE
    assert toks[1].value is False


def test_multi_char_operators_maximal_munch():
    assert kinds(":= -> :> /. |> == != <= >= ..") == [
        TokenKind.DEFINE,
        TokenKind.ARROW,
        TokenKind.DELAYED_ARROW,
        TokenKind.REPLACE,
        TokenKind.PIPE,
        TokenKind.EQ,
        TokenKind.NEQ,
        TokenKind.LTE,
        TokenKind.GTE,
        TokenKind.RANGE,
        TokenKind.EOF,
    ]


def test_identifiers_including_blanks():
    toks = tokenize("x _ _int __ ___ myFunc2")
    assert [t.text for t in toks[:-1]] == ["x", "_", "_int", "__", "___", "myFunc2"]
    assert all(t.kind is TokenKind.IDENT for t in toks[:-1])


def test_block_comments_are_skipped_and_can_nest():
    toks = tokenize("1 (* a comment (* nested *) still going *) + 2")
    assert [t.kind for t in toks] == [
        TokenKind.INT,
        TokenKind.PLUS,
        TokenKind.INT,
        TokenKind.EOF,
    ]


def test_delimiters_and_punctuation():
    assert kinds("(){}[],:;") == [
        TokenKind.LPAREN,
        TokenKind.RPAREN,
        TokenKind.LBRACE,
        TokenKind.RBRACE,
        TokenKind.LBRACKET,
        TokenKind.RBRACKET,
        TokenKind.COMMA,
        TokenKind.COLON,
        TokenKind.SEMICOLON,
        TokenKind.EOF,
    ]
