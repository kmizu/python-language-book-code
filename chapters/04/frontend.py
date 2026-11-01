"""第4章のまめ言語。ここまでに導入した構文だけを扱う。"""

from dataclasses import dataclass
from chapter01 import Token
from chapter02 import Number, Unary, Binary, ParseError


@dataclass
class Name:
    name: str
    pos: int


@dataclass
class Let:
    name: str
    value: object
    pos: int


@dataclass
class Assign:
    name: str
    value: object
    pos: int


@dataclass
class ExprStmt:
    value: object
    pos: int


@dataclass
class Program:
    functions: dict
    body: list


KEYWORDS = {word: word.upper() for word in ('let',)}
SYMBOLS = {
    "+": "PLUS", "-": "MINUS", "*": "STAR",
    "(": "LPAREN", ")": "RPAREN",
    ";": "SEMICOLON", "=": "ASSIGN",
}


def is_letter(ch):
    return "a" <= ch <= "z" or "A" <= ch <= "Z"


def lex(source):
    tokens = []
    i = 0
    while i < len(source):
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "#":
            while i < len(source) and source[i] != "\n":
                i += 1
            continue
        if "0" <= ch <= "9":
            start = i
            while i < len(source) and "0" <= source[i] <= "9":
                i += 1
            tokens.append(Token("INT", source[start:i], start))
            continue
        if is_letter(ch):
            start = i
            while i < len(source) and (
                is_letter(source[i]) or "0" <= source[i] <= "9" or source[i] == "_"
            ):
                i += 1
            text = source[start:i]
            tokens.append(Token(KEYWORDS.get(text, "NAME"), text, start))
            continue
        if ch in SYMBOLS:
            tokens.append(Token(SYMBOLS[ch], ch, i))
            i += 1
            continue
        raise ValueError(f"{i + 1}文字目の{ch!r}は読めません")
    tokens.append(Token("EOF", "", len(source)))
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0

    def current(self):
        return self.tokens[self.index]

    def advance(self):
        token = self.current()
        self.index += 1
        return token

    def fail(self, expected):
        token = self.current()
        found = "入力の終わり" if token.kind == "EOF" else repr(token.text)
        raise ParseError(f"{token.pos + 1}文字目: {expected}が必要です（{found}）")

    def expect(self, kind, expected=None):
        if self.current().kind != kind:
            self.fail(expected or kind)
        return self.advance()

    def parse(self):
        body = []
        while self.current().kind != "EOF":
            body.append(self.parse_statement())
        return Program({}, body)

    def parse_statement(self):
        token = self.current()
        if token.kind == "LET":
            self.advance()
            name = self.expect("NAME", "変数名").text
            self.expect("ASSIGN", "'='")
            value = self.parse_expression()
            self.expect("SEMICOLON", "';'")
            return Let(name, value, token.pos)
        if token.kind == "NAME" and self.tokens[self.index + 1].kind == "ASSIGN":
            self.advance()
            self.advance()
            value = self.parse_expression()
            self.expect("SEMICOLON", "';'")
            return Assign(token.text, value, token.pos)
        value = self.parse_expression()
        self.expect("SEMICOLON", "';'")
        return ExprStmt(value, token.pos)

    def parse_expression(self):
        node = self.parse_term()
        while self.current().kind in ("PLUS", "MINUS"):
            operator = self.advance()
            node = Binary(operator.text, node, self.parse_term(), operator.pos)
        return node

    def parse_term(self):
        node = self.parse_unary()
        while self.current().kind == "STAR":
            operator = self.advance()
            node = Binary(operator.text, node, self.parse_unary(), operator.pos)
        return node

    def parse_unary(self):
        token = self.current()
        if token.kind in ("PLUS", "MINUS"):
            self.advance()
            return Unary(token.text, self.parse_unary(), token.pos)
        return self.parse_primary()

    def parse_primary(self):
        token = self.current()
        if token.kind == "INT":
            self.advance()
            return Number(int(token.text), token.pos)
        if token.kind == "NAME":
            self.advance()
            return Name(token.text, token.pos)
        if token.kind == "LPAREN":
            self.advance()
            node = self.parse_expression()
            self.expect("RPAREN", "')'")
            return node
        self.fail("整数、名前、または'('")


def parse_program(source):
    return Parser(lex(source)).parse()
