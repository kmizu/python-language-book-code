"""構文木をたどって実行する、まめ言語の基準実装。"""

from dataclasses import dataclass
from frontend import (Number, Unary, Binary, Name, Call, Let, Assign,
                      Print, Return, If, While, ExprStmt)


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


class UndefinedFunctionError(LanguageRuntimeError):
    def __init__(self, name, pos=0):
        self.name = name
        super().__init__(f"関数{name!r}は定義されていません", pos)


class ArityError(LanguageRuntimeError):
    def __init__(self, name, expected, actual, pos=0):
        self.name = name
        self.expected = expected
        self.actual = actual
        super().__init__(f"関数{name!r}の引数は{expected}個です（実際は{actual}個）", pos)


class ReturnSignal(Exception):
    """言語のエラーではなく、ブロックを抜けるための内部の合図。"""
    def __init__(self, value):
        self.value = value


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
    if op == "<":
        return int(left < right)
    if op == "<=":
        return int(left <= right)
    if op == ">":
        return int(left > right)
    if op == ">=":
        return int(left >= right)
    if op == "==":
        return int(left == right)
    if op == "!=":
        return int(left != right)
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

    def call(self, name, args, pos=0):
        if name not in self.program.functions:
            raise UndefinedFunctionError(name, pos)
        function = self.program.functions[name]
        if len(args) != len(function.params):
            raise ArityError(name, len(function.params), len(args), pos)
        # 呼出しごとに新しい辞書を作り、呼出し元やグローバルを連結しない。
        local = dict(zip(function.params, args))
        try:
            self.execute_block(function.body, local)
        except ReturnSignal as signal:
            return signal.value
        return 0

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
        if isinstance(node, Call):
            args = [self.expr(arg, env) for arg in node.args]
            return self.call(node.name, args, node.pos)
        raise TypeError(f"知らない式です: {type(node).__name__}")

    def execute_block(self, body, env):
        for statement in body:
            self.execute(statement, env)

    def execute(self, node, env):
        if isinstance(node, Let):
            env[node.name] = self.expr(node.value, env)
        elif isinstance(node, Assign):
            # 右辺を先に評価する。代入先検査の順もVMとそろえる。
            value = self.expr(node.value, env)
            if node.name not in env:
                raise UndefinedNameError(node.name, node.pos)
            env[node.name] = value
        elif isinstance(node, Print):
            self.output.append(self.expr(node.value, env))
        elif isinstance(node, Return):
            raise ReturnSignal(self.expr(node.value, env))
        elif isinstance(node, If):
            branch = node.then_body if self.expr(node.condition, env) != 0 else node.else_body
            self.execute_block(branch, env)
        elif isinstance(node, While):
            while self.expr(node.condition, env) != 0:
                self.execute_block(node.body, env)
        elif isinstance(node, ExprStmt):
            self.expr(node.value, env)
        else:
            raise TypeError(f"知らない文です: {type(node).__name__}")
