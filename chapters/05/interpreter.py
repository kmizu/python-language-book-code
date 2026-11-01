"""第5章の構文木をたどるインタプリタ。"""

from dataclasses import dataclass
from frontend import (Number, Unary, Binary, Name, Let, Assign, Print, If, ExprStmt)


@dataclass
class Result:
    output: list
    globals: dict


class LanguageRuntimeError(Exception):
    def __init__(self, message, pos=0):
        self.pos = pos
        super().__init__(f"{pos + 1}文字目: {message}")


class UndefinedNameError(LanguageRuntimeError):
    def __init__(self, name, pos=0):
        self.name = name
        super().__init__(f"変数{name!r}は定義されていません", pos)


def apply_unary(op, value):
    if op == "+":
        return +value
    if op == "-":
        return -value
    raise ValueError(f"未対応の単項演算子です: {op}")


def apply_binary(op, left, right):
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    raise ValueError(f"未対応の二項演算子です: {op}")


class Interpreter:
    def __init__(self, program):
        self.program = program
        self.output = []
        self.globals = {}

    def run(self):
        self.output = []
        self.globals = {}
        self.execute_block(self.program.body, self.globals)
        return Result(list(self.output), dict(self.globals))

    def expr(self, node, env):
        if isinstance(node, Number):
            return node.value
        if isinstance(node, Name):
            if node.name not in env:
                raise UndefinedNameError(node.name, node.pos)
            return env[node.name]
        if isinstance(node, Unary):
            return apply_unary(node.op, self.expr(node.operand, env))
        if isinstance(node, Binary):
            left = self.expr(node.left, env)
            right = self.expr(node.right, env)
            return apply_binary(node.op, left, right)
        raise TypeError(f"知らない式です: {type(node).__name__}")

    def execute_block(self, body, env):
        for statement in body:
            self.execute(statement, env)

    def execute(self, node, env):
        if isinstance(node, Let):
            env[node.name] = self.expr(node.value, env)
        elif isinstance(node, Assign):
            value = self.expr(node.value, env)
            if node.name not in env:
                raise UndefinedNameError(node.name, node.pos)
            env[node.name] = value
        elif isinstance(node, Print):
            self.output.append(self.expr(node.value, env))
        elif isinstance(node, If):
            branch = node.then_body if self.expr(node.condition, env) != 0 else node.else_body
            self.execute_block(branch, env)
        elif isinstance(node, ExprStmt):
            self.expr(node.value, env)
        else:
            raise TypeError(f"知らない文です: {type(node).__name__}")
