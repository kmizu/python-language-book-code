from chapter01 import lex


class Number:
    def __init__(self, value, pos):
        self.value = value
        self.pos = pos


class Unary:
    def __init__(self, op, operand, pos):
        self.op = op
        self.operand = operand
        self.pos = pos


class Binary:
    def __init__(self, op, left, right, pos):
        self.op = op
        self.left = left
        self.right = right
        self.pos = pos


class ParseError(Exception):
    pass


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
        if token.kind == "EOF":
            detail = "入力が終わりました"
        else:
            detail = f"{token.text!r}が見つかりました"
        raise ParseError(
            f"{token.pos + 1}文字目: {expected}が必要です（{detail}）"
        )

    def expect(self, kind, expected):
        if self.current().kind != kind:
            self.fail(expected)
        return self.advance()

    def parse_primary(self):
        token = self.current()
        if token.kind == "INT":
            self.advance()
            return Number(int(token.text), token.pos)
        if token.kind == "LPAREN":
            self.advance()
            node = self.parse_expression()
            self.expect("RPAREN", "閉じかっこ ')'")
            return node
        self.fail("整数か開きかっこ '('")

    def parse_unary(self):
        token = self.current()
        if token.kind in ("PLUS", "MINUS"):
            self.advance()
            operand = self.parse_unary()
            return Unary(token.text, operand, token.pos)
        return self.parse_primary()

    def parse_term(self):
        node = self.parse_unary()
        while self.current().kind == "STAR":
            operator = self.advance()
            right = self.parse_unary()
            node = Binary(operator.text, node, right, operator.pos)
        return node

    def parse_expression(self):
        node = self.parse_term()
        while self.current().kind in ("PLUS", "MINUS"):
            operator = self.advance()
            right = self.parse_term()
            node = Binary(operator.text, node, right, operator.pos)
        return node

    def parse(self):
        node = self.parse_expression()
        self.expect("EOF", "式の終わり")
        return node


def parse(source):
    tokens = lex(source)
    parser = Parser(tokens)
    return parser.parse()


def show_tree(node, indent=0):
    padding = "  " * indent
    if isinstance(node, Number):
        print(f"{padding}Number({node.value})")
    elif isinstance(node, Unary):
        print(f"{padding}Unary({node.op})")
        show_tree(node.operand, indent + 1)
    elif isinstance(node, Binary):
        print(f"{padding}Binary({node.op})")
        show_tree(node.left, indent + 1)
        show_tree(node.right, indent + 1)
    else:
        raise TypeError(f"知らないノードです: {type(node).__name__}")


if __name__ == "__main__":
    tree = parse("100 + 80 * 3")
    show_tree(tree)
