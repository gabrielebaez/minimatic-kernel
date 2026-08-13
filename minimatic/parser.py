"""
Parser - Recursive descent + precedence climbing, source text -> AST.

No semantic work happens here (kernel doc §3): no head resolution, no
attribute lookups, no dispatch. The parser's only job is to produce a tree
of Symbol / atom / Expression / pattern nodes with all surface sugar
desugared, per the tables in IMPLEMENTATION_PLAN.md.

Precedence, low to high:
    pipe (|>, //)  >  arrow (->, :>)  >  replace (/.)  >  comparison
    >  additive  >  multiplicative  >  map (/@, right-assoc)
    >  power (^, right-assoc)  >  unary (-)  >  call  >  primary

The two Wolfram-inherited operators sit at the levels their Wolfram
counterparts do relative to the rest of the grammar: `//` (postfix
application) binds loosest, alongside `|>` — which it is a spelling of,
down to the same `__pipe__` desugaring, so `a // f(b)` splices `a` into
first position exactly like `a |> f(b)`. `/@` (map) binds tighter than
arithmetic and looser than `^`, so `f /@ xs * 2` is `(f /@ xs) * 2` and
`f /@ g /@ xs` is `f /@ (g /@ xs)`.

`/.` gets its own dedicated rule sub-grammar (parse_single_rule /
parse_rule_rhs) rather than reusing the general arrow parser, because a
rewrite rule's `->` must always build a Rule (never a Lambda) and must bind
tighter than a Lambda arrow that might enclose it — e.g.
`x -> x /. "N/A" -> 0` must parse as `Lambda(x, ReplaceAll(x, Rule("N/A", 0)))`,
not `Lambda(x, ReplaceAll(x, "N/A")) -> 0`.
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.patterns import Blank, BlankNullSeq, BlankSeq, PatternBind
from .ast.symbol import Symbol, symbol
from .errors import MinimaticSyntaxError, NotImplementedInMVPError
from .lexer import Token, TokenKind, tokenize

_COMPARISON_OPS = {
    TokenKind.EQ: "equal",
    TokenKind.NEQ: "not_equal",
    TokenKind.LT: "less",
    TokenKind.GT: "greater",
    TokenKind.LTE: "less_eq",
    TokenKind.GTE: "greater_eq",
}

_ADDITIVE_OPS = {
    TokenKind.PLUS: "plus",
    TokenKind.MINUS: "minus",
}

_MULTIPLICATIVE_OPS = {
    TokenKind.STAR: "times",
    TokenKind.SLASH: "divide",
    TokenKind.PERCENT: "mod",
}


def parse(source: str):
    return Parser(tokenize(source)).parse_program()


def parse_all(source: str) -> list:
    """
    Parse zero or more top-level statements from `source`, in order.

    Unlike `parse` (which requires exactly one statement followed by EOF),
    this is what running a *script* needs: statements are self-delimiting
    (each `parse_expr()` call naturally stops where the next one begins,
    since the grammar has no implicit-application/juxtaposition case), so
    no explicit separator between them is required — a multi-line
    expression like a `|>` chain still parses as a single statement.
    """
    parser = Parser(tokenize(source))
    statements = []
    while not parser._at(TokenKind.EOF):
        statements.append(parser.parse_expr())
    return statements


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    # -- token helpers --------------------------------------------------

    def _peek(self) -> Token:
        return self.tokens[self.i]

    def _at(self, kind: TokenKind) -> bool:
        return self.tokens[self.i].kind is kind

    def _advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _expect(self, kind: TokenKind) -> Token:
        if not self._at(kind):
            tok = self._peek()
            raise MinimaticSyntaxError(
                f"expected {kind.name}, got {tok.kind.name} ({tok.text!r}) "
                f"at position {tok.pos}"
            )
        return self._advance()

    # -- entry point ------------------------------------------------------

    def parse_program(self):
        expr = self.parse_expr()
        self._expect(TokenKind.EOF)
        return expr

    # -- top level: `=` / `:=` bind loosest of all ------------------------

    def parse_expr(self):
        left = self.parse_pipe()
        if self._at(TokenKind.ASSIGN):
            self._advance()
            if not isinstance(left, Symbol):
                raise MinimaticSyntaxError(
                    "left-hand side of '=' must be a plain symbol in the MVP kernel"
                )
            rhs = self.parse_expr()
            return Expression(symbol("Set"), left, rhs)
        if self._at(TokenKind.DEFINE):
            self._advance()
            rhs = self.parse_expr()
            return Expression(symbol("SetDelayed"), left, rhs)
        return left

    # -- level 1: pipe (|>, //) (left-assoc) -------------------------------

    def parse_pipe(self):
        left = self.parse_arrow()
        while self._at(TokenKind.PIPE) or self._at(TokenKind.POSTFIX):
            self._advance()
            right = self.parse_arrow()
            left = Expression(symbol("__pipe__"), left, right)
        return left

    # -- level 2: arrow (right-assoc; Lambda if LHS is a bare Symbol, else Rule) --

    def parse_arrow(self):
        left = self.parse_replace()
        if self._at(TokenKind.ARROW) or self._at(TokenKind.DELAYED_ARROW):
            delayed = self._at(TokenKind.DELAYED_ARROW)
            self._advance()
            right = self.parse_arrow()
            if delayed:
                raise NotImplementedInMVPError("RuleDelayed (:>)")
            if isinstance(left, Symbol):
                return Expression(symbol("Lambda"), left, right)
            return Expression(symbol("Rule"), left, right)
        return left

    # -- level 3: /. ReplaceAll --------------------------------------------

    def parse_replace(self):
        left = self.parse_comparison()
        while self._at(TokenKind.REPLACE):
            self._advance()
            rules = self.parse_rule_rhs()
            left = Expression(symbol("ReplaceAll"), left, rules)
        return left

    def parse_rule_rhs(self):
        """The right side of `/.`: either `[rule, rule, ...]` or a single rule."""
        if self._at(TokenKind.LBRACKET):
            self._advance()
            rules = []
            if not self._at(TokenKind.RBRACKET):
                rules.append(self.parse_single_rule())
                while self._at(TokenKind.COMMA):
                    self._advance()
                    if self._at(TokenKind.RBRACKET):
                        break
                    rules.append(self.parse_single_rule())
            self._expect(TokenKind.RBRACKET)
            return Expression(symbol("List"), *rules)
        return self.parse_single_rule()

    def parse_single_rule(self):
        """`pattern -> expr` or `pattern :> expr` — always a Rule, never a Lambda.
        Used by `/.` and by dict-literal entries."""
        lhs = self.parse_comparison()
        if self._at(TokenKind.DELAYED_ARROW):
            self._advance()
            raise NotImplementedInMVPError("RuleDelayed (:>)")
        self._expect(TokenKind.ARROW)
        rhs = self.parse_replace()
        return Expression(symbol("Rule"), lhs, rhs)

    # -- level 4: comparison -----------------------------------------------

    def parse_comparison(self):
        left = self.parse_range()
        while self._peek().kind in _COMPARISON_OPS:
            op = _COMPARISON_OPS[self._advance().kind]
            right = self.parse_range()
            left = Expression(symbol(op), left, right)
        return left

    # -- level 4.5: range (`..`, half-open: `0..5` -> [0,1,2,3,4]) -----------

    def parse_range(self):
        left = self.parse_additive()
        if self._at(TokenKind.RANGE):
            self._advance()
            right = self.parse_additive()
            return Expression(symbol("Range"), left, right)
        return left

    # -- level 5: additive ---------------------------------------------------

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self._peek().kind in _ADDITIVE_OPS:
            op = _ADDITIVE_OPS[self._advance().kind]
            right = self.parse_multiplicative()
            left = Expression(symbol(op), left, right)
        return left

    # -- level 6: multiplicative ----------------------------------------------

    def parse_multiplicative(self):
        left = self.parse_map()
        while self._peek().kind in _MULTIPLICATIVE_OPS:
            op = _MULTIPLICATIVE_OPS[self._advance().kind]
            right = self.parse_map()
            left = Expression(symbol(op), left, right)
        return left

    # -- level 6.5: map (/@, right-assoc) --------------------------------------

    def parse_map(self):
        """`f /@ xs` -> `map(xs, f)`.

        Written function-first (Wolfram's `Map[f, xs]` order), desugared
        into the prelude's list-first `map` — so `f /@ xs` and
        `xs |> map(f)` produce the identical tree, and `/@` stays a pure
        spelling of `map` rather than a second implementation of it."""
        left = self.parse_power()
        if self._at(TokenKind.MAP):
            self._advance()
            right = self.parse_map()  # right-assoc: `f /@ g /@ xs`
            return Expression(symbol("map"), right, left)
        return left

    # -- level 7: power (right-assoc) ------------------------------------------

    def parse_power(self):
        left = self.parse_unary()
        if self._at(TokenKind.CARET):
            self._advance()
            right = self.parse_power()
            return Expression(symbol("power"), left, right)
        return left

    # -- level 8: unary minus --------------------------------------------------

    def parse_unary(self):
        if self._at(TokenKind.MINUS):
            self._advance()
            operand = self.parse_unary()
            return Expression(symbol("negate"), operand)
        return self.parse_call()

    # -- level 9: call application ----------------------------------------------

    def parse_call(self):
        expr = self.parse_primary()
        while self._at(TokenKind.LPAREN):
            self._advance()
            args = self.parse_arg_list()
            self._expect(TokenKind.RPAREN)
            if not isinstance(expr, (Symbol, Expression)):
                raise MinimaticSyntaxError(
                    f"cannot call {expr!r} — a call's head must be a Symbol or Expression"
                )
            expr = Expression(expr, *args)
        return expr

    def parse_arg_list(self):
        args = []
        if self._at(TokenKind.RPAREN):
            return args
        args.append(self.parse_arg())
        while self._at(TokenKind.COMMA):
            self._advance()
            if self._at(TokenKind.RPAREN):
                break
            args.append(self.parse_arg())
        return args

    def parse_arg(self):
        return self.parse_pipe()

    # -- level 10: primary ---------------------------------------------------

    def parse_primary(self):
        tok = self._peek()

        if tok.kind is TokenKind.INT or tok.kind is TokenKind.FLOAT:
            self._advance()
            return tok.value

        if tok.kind is TokenKind.STRING:
            self._advance()
            return tok.value

        if tok.kind is TokenKind.TRUE or tok.kind is TokenKind.FALSE:
            self._advance()
            return tok.value

        if tok.kind is TokenKind.LPAREN:
            self._advance()
            first = self.parse_pipe()
            if self._at(TokenKind.SEMICOLON):
                # `(stmt1; stmt2; ...)` -> CompoundExpression: evaluate each
                # in order for effect, the value is the last one.
                exprs = [first]
                while self._at(TokenKind.SEMICOLON):
                    self._advance()
                    if self._at(TokenKind.RPAREN):
                        break  # trailing semicolon allowed
                    exprs.append(self.parse_pipe())
                self._expect(TokenKind.RPAREN)
                return Expression(symbol("CompoundExpression"), *exprs)
            self._expect(TokenKind.RPAREN)
            return first

        if tok.kind is TokenKind.LBRACKET:
            return self.parse_list_literal()

        if tok.kind is TokenKind.LBRACE:
            return self.parse_dict_literal()

        if tok.kind is TokenKind.DOLLAR:
            # The pipe's placeholder, `a |> f($, b)`. Parsed as an ordinary
            # Symbol so it travels through the held right-hand side
            # unchanged; `__pipe__` is what gives it meaning (prelude.py).
            # It is unforgeable as a user identifier — the IDENT scanner
            # does not accept `$`.
            self._advance()
            return symbol("$")

        if tok.kind is TokenKind.IDENT:
            return self.parse_ident_or_pattern()

        raise MinimaticSyntaxError(
            f"unexpected token {tok.kind.name} ({tok.text!r}) at position {tok.pos}"
        )

    def parse_ident_or_pattern(self):
        tok = self._advance()
        name = tok.text

        blank = _try_parse_blank(name)
        if blank is not None:
            return blank

        if self._at(TokenKind.COLON):
            self._advance()
            inner = self.parse_unary()
            return PatternBind(name, inner)

        return symbol(name)

    def parse_list_literal(self):
        self._expect(TokenKind.LBRACKET)
        items = []
        if not self._at(TokenKind.RBRACKET):
            items.append(self.parse_pipe())
            while self._at(TokenKind.COMMA):
                self._advance()
                if self._at(TokenKind.RBRACKET):
                    break
                items.append(self.parse_pipe())
        self._expect(TokenKind.RBRACKET)
        return Expression(symbol("List"), *items)

    def parse_dict_literal(self):
        self._expect(TokenKind.LBRACE)
        rules = []
        if not self._at(TokenKind.RBRACE):
            rules.append(self.parse_single_rule())
            while self._at(TokenKind.COMMA):
                self._advance()
                if self._at(TokenKind.RBRACE):
                    break
                rules.append(self.parse_single_rule())
        self._expect(TokenKind.RBRACE)
        return Expression(symbol("Dict"), *rules)


def _try_parse_blank(text: str):
    """
    `_`, `_int`, `__`, `__int`, `___`, `___int` -> Blank/BlankSeq/BlankNullSeq.
    Anything else (including names like `__pipe__` whose non-underscore
    remainder isn't a clean alphanumeric type tag) is an ordinary identifier.
    """
    leading = len(text) - len(text.lstrip("_"))
    if leading == 0 or leading > 3:
        return None
    remainder = text[leading:]
    if remainder and not remainder.isalnum():
        return None
    type_tag = remainder or None
    if leading == 1:
        return Blank(type_tag)
    if leading == 2:
        return BlankSeq(type_tag)
    return BlankNullSeq(type_tag)
