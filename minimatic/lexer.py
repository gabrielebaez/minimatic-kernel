"""
Lexer - Tokenizes Minimatic source text.

An iterative character scanner, no external lexer generator. Produces a
flat list of Tokens; `(* ... *)` block comments (which may nest) are
consumed and never emitted as tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .errors import MinimaticSyntaxError


class TokenKind(Enum):
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    TRUE = auto()
    FALSE = auto()
    IDENT = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    CARET = auto()
    PERCENT = auto()

    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()

    ARROW = auto()  # ->
    DELAYED_ARROW = auto()  # :>
    REPLACE = auto()  # /.
    PIPE = auto()  # |>
    POSTFIX = auto()  # //
    MAP = auto()  # /@
    RANGE = auto()  # ..
    AMP = auto()  # &
    DOLLAR = auto()  # $ — the pipe's placeholder (a |> f($, b))

    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()

    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()

    DEFINE = auto()  # :=
    ASSIGN = auto()  # =

    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    value: object = None
    pos: int = 0

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.text!r})"


_KEYWORDS = {
    "True": TokenKind.TRUE,
    "False": TokenKind.FALSE,
}

# Multi-character operators, longest first so maximal munch is a linear scan.
_MULTI_CHAR_OPS: list[tuple[str, TokenKind]] = [
    (":=", TokenKind.DEFINE),
    ("->", TokenKind.ARROW),
    (":>", TokenKind.DELAYED_ARROW),
    ("/.", TokenKind.REPLACE),
    ("//", TokenKind.POSTFIX),
    ("/@", TokenKind.MAP),
    ("|>", TokenKind.PIPE),
    ("..", TokenKind.RANGE),
    ("==", TokenKind.EQ),
    ("!=", TokenKind.NEQ),
    ("<=", TokenKind.LTE),
    (">=", TokenKind.GTE),
]

_SINGLE_CHAR_OPS: dict[str, TokenKind] = {
    ":": TokenKind.COLON,
    "=": TokenKind.ASSIGN,
    "<": TokenKind.LT,
    ">": TokenKind.GT,
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "^": TokenKind.CARET,
    "%": TokenKind.PERCENT,
    "&": TokenKind.AMP,
    "$": TokenKind.DOLLAR,
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    "[": TokenKind.LBRACKET,
    "]": TokenKind.RBRACKET,
    "{": TokenKind.LBRACE,
    "}": TokenKind.RBRACE,
    ",": TokenKind.COMMA,
    ";": TokenKind.SEMICOLON,
}


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_cont(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.i = 0
        self.n = len(source)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while True:
            self._skip_whitespace_and_comments()
            if self.i >= self.n:
                tokens.append(Token(TokenKind.EOF, "", pos=self.i))
                return tokens
            tokens.append(self._next_token())

    def _skip_whitespace_and_comments(self) -> None:
        while self.i < self.n:
            ch = self.source[self.i]
            if ch.isspace():
                self.i += 1
                continue
            if self.source.startswith("(*", self.i):
                self._skip_block_comment()
                continue
            break

    def _skip_block_comment(self) -> None:
        start = self.i
        depth = 0
        while self.i < self.n:
            if self.source.startswith("(*", self.i):
                depth += 1
                self.i += 2
                continue
            if self.source.startswith("*)", self.i):
                depth -= 1
                self.i += 2
                if depth == 0:
                    return
                continue
            self.i += 1
        raise MinimaticSyntaxError(f"unterminated block comment starting at position {start}")

    def _next_token(self) -> Token:
        start = self.i
        ch = self.source[self.i]

        if ch.isdigit():
            return self._read_number()

        if ch == '"':
            return self._read_string()

        if _is_ident_start(ch):
            return self._read_ident()

        for op_text, kind in _MULTI_CHAR_OPS:
            if self.source.startswith(op_text, self.i):
                self.i += len(op_text)
                return Token(kind, op_text, pos=start)

        if ch in _SINGLE_CHAR_OPS:
            self.i += 1
            return Token(_SINGLE_CHAR_OPS[ch], ch, pos=start)

        raise MinimaticSyntaxError(f"unexpected character {ch!r} at position {start}")

    def _read_number(self) -> Token:
        start = self.i
        while self.i < self.n and self.source[self.i].isdigit():
            self.i += 1

        is_float = False
        if self.i + 1 < self.n and self.source[self.i] == "." and self.source[self.i + 1].isdigit():
            is_float = True
            self.i += 1
            while self.i < self.n and self.source[self.i].isdigit():
                self.i += 1

        if self.i < self.n and self.source[self.i] in "eE":
            save = self.i
            j = self.i + 1
            if j < self.n and self.source[j] in "+-":
                j += 1
            if j < self.n and self.source[j].isdigit():
                is_float = True
                self.i = j
                while self.i < self.n and self.source[self.i].isdigit():
                    self.i += 1
            else:
                self.i = save

        text = self.source[start : self.i]
        if is_float:
            return Token(TokenKind.FLOAT, text, value=float(text), pos=start)
        return Token(TokenKind.INT, text, value=int(text), pos=start)

    def _read_string(self) -> Token:
        start = self.i
        self.i += 1  # opening quote
        chars: list[str] = []
        while True:
            if self.i >= self.n:
                raise MinimaticSyntaxError(f"unterminated string starting at position {start}")
            ch = self.source[self.i]
            if ch == '"':
                self.i += 1
                break
            if ch == "\\" and self.i + 1 < self.n:
                nxt = self.source[self.i + 1]
                escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                chars.append(escapes.get(nxt, nxt))
                self.i += 2
                continue
            chars.append(ch)
            self.i += 1
        text = self.source[start : self.i]
        return Token(TokenKind.STRING, text, value="".join(chars), pos=start)

    def _read_ident(self) -> Token:
        start = self.i
        self.i += 1
        while self.i < self.n and _is_ident_cont(self.source[self.i]):
            self.i += 1
        text = self.source[start : self.i]
        if text in _KEYWORDS:
            kind = _KEYWORDS[text]
            value = True if kind is TokenKind.TRUE else False
            return Token(kind, text, value=value, pos=start)
        return Token(TokenKind.IDENT, text, pos=start)


def tokenize(source: str) -> list[Token]:
    return Lexer(source).tokenize()
