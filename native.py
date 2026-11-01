"""A small, real LLVM JIT with an intentionally expensive safety preflight.

Only a single pure return expression is supported.  Python first checks every
input and intermediate value using arbitrary precision integers.  Machine code
is entered only when the whole calculation fits signed 64 bits.  This teaches
the native boundary without changing the language's integer semantics; it does
not promise a speedup.  No Python C API is called from generated code.
"""
import ctypes

from frontend import Number, Unary, Binary, Name, Return

_backend_import_error = None
try:
    from llvmlite import binding as llvm, ir
except (ImportError, OSError) as error:
    llvm = None
    ir = None
    _backend_import_error = error


MIN_INT = -(1 << 63)
MAX_INT = (1 << 63) - 1
ARITHMETIC = {"+", "-", "*"}
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}
_backend_ready = False


class UnsupportedNative(ValueError):
    """The function is valid for the VM, but outside this JIT's subset."""


class NativeUnavailable(RuntimeError):
    """The optional LLVM backend or executable memory is unavailable."""


class OutsideRange(Exception):
    pass


def checked_value(value):
    if type(value) is not int or not MIN_INT <= value <= MAX_INT:
        raise OutsideRange()
    return value


def preflight(node, env):
    """Compute the pure expression and reject *any* out-of-range value."""
    if isinstance(node, Number):
        return checked_value(node.value)
    if isinstance(node, Name):
        return checked_value(env[node.name])
    if isinstance(node, Unary):
        value = preflight(node.operand, env)
        return checked_value(+value if node.op == "+" else -value)
    left = preflight(node.left, env)
    right = preflight(node.right, env)
    if node.op == "+":
        value = left + right
    elif node.op == "-":
        value = left - right
    elif node.op == "*":
        value = left * right
    elif node.op == "<":
        value = int(left < right)
    elif node.op == "<=":
        value = int(left <= right)
    elif node.op == ">":
        value = int(left > right)
    elif node.op == ">=":
        value = int(left >= right)
    elif node.op == "==":
        value = int(left == right)
    else:  # Validation guarantees this is !=.
        value = int(left != right)
    return checked_value(value)


def validate_expression(node, params):
    if isinstance(node, Number):
        if type(node.value) is not int:
            raise UnsupportedNative("整数以外のNumberです")
        return
    if isinstance(node, Name):
        if node.name not in params:
            raise UnsupportedNative(f"引数以外の名前です: {node.name}")
        return
    if isinstance(node, Unary) and node.op in {"+", "-"}:
        validate_expression(node.operand, params)
        return
    if isinstance(node, Binary) and node.op in ARITHMETIC | COMPARISONS:
        validate_expression(node.left, params)
        validate_expression(node.right, params)
        return
    raise UnsupportedNative(f"対応外の式です: {type(node).__name__}")


def initialize_backend():
    global _backend_ready
    if _backend_ready:
        return
    if llvm is None:
        detail = f"{type(_backend_import_error).__name__}: {_backend_import_error}"
        raise NativeUnavailable(
            f"llvmliteを読み込めません（{detail}）。通常VMは利用できます"
        ) from _backend_import_error
    try:
        # The book's tested environment uses llvmlite 0.43 / LLVM 14.
        # Newer llvmlite releases initialize the LLVM core automatically.
        import llvmlite
        version = tuple(int(part) for part in llvmlite.__version__.split(".")[:2])
        if version < (0, 45):
            llvm.initialize()
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        llvm.check_jit_execution()
    except (RuntimeError, OSError) as error:
        raise NativeUnavailable(f"native実行を準備できません: {error}") from error
    _backend_ready = True


def emit_expression(node, builder, env):
    integer = ir.IntType(64)
    if isinstance(node, Number):
        return ir.Constant(integer, node.value)
    if isinstance(node, Name):
        return env[node.name]
    if isinstance(node, Unary):
        value = emit_expression(node.operand, builder, env)
        if node.op == "+":
            return value
        return builder.sub(ir.Constant(integer, 0), value, name="neg")
    left = emit_expression(node.left, builder, env)
    right = emit_expression(node.right, builder, env)
    if node.op == "+":
        return builder.add(left, right, name="add")
    if node.op == "-":
        return builder.sub(left, right, name="sub")
    if node.op == "*":
        return builder.mul(left, right, name="mul")
    comparison = builder.icmp_signed(node.op, left, right, name="compare")
    return builder.zext(comparison, integer, name="boolean_as_integer")


class NativeFunction:
    def __init__(self, function, constants=None):
        if len(function.body) != 1 or not isinstance(function.body[0], Return):
            raise UnsupportedNative("return式1個の関数だけをnativeにできます")
        if len(set(function.params)) != len(function.params):
            raise UnsupportedNative("引数名が重複しています")
        self.function = function
        self.params = tuple(function.params)
        self.expression = function.body[0].value
        validate_expression(self.expression, set(self.params))
        self.constants = dict(constants or {})
        for name, value in self.constants.items():
            if name not in self.params:
                raise UnsupportedNative(f"引数以外を特殊化できません: {name}")
            try:
                checked_value(value)
            except OutsideRange:
                raise UnsupportedNative("特殊化する定数はsigned64整数が必要です")
        initialize_backend()
        integer = ir.IntType(64)
        module = ir.Module(name="mame")
        module.triple = llvm.get_default_triple()
        self.target_machine = llvm.Target.from_default_triple().create_target_machine()
        module.data_layout = str(self.target_machine.target_data)
        signature = ir.FunctionType(integer, [integer] * len(self.params))
        entry = ir.Function(module, signature, name="mame_entry")
        env = {}
        for name, argument in zip(self.params, entry.args):
            argument.name = name
            env[name] = (ir.Constant(integer, self.constants[name])
                         if name in self.constants else argument)
        builder = ir.IRBuilder(entry.append_basic_block("entry"))
        builder.ret(emit_expression(self.expression, builder, env))
        self.llvm_ir = str(module)
        try:
            self.module = llvm.parse_assembly(self.llvm_ir)
            self.module.verify()
            backing = llvm.parse_assembly("")
            self.engine = llvm.create_mcjit_compiler(backing, self.target_machine)
            self.engine.add_module(self.module)
            self.engine.finalize_object()
            self.address = self.engine.get_function_address("mame_entry")
        except (RuntimeError, OSError) as error:
            raise NativeUnavailable(f"機械語を作れません: {error}") from error
        if not self.address:
            raise NativeUnavailable("native関数のアドレスを取得できません")
        prototype = ctypes.CFUNCTYPE(ctypes.c_int64,
                                     *([ctypes.c_int64] * len(self.params)))
        self.cfunc = prototype(self.address)
        # engine, module, target machine and cfunc stay alive with this object.
        self.native_calls = 0

    def try_call(self, args):
        args = tuple(args)
        if len(args) != len(self.params):
            return False, None
        try:
            for value in args:
                checked_value(value)
            env = dict(zip(self.params, args))
            if any(env[name] != value for name, value in self.constants.items()):
                return False, None
            preflight(self.expression, env)
        except OutsideRange:
            return False, None
        value = int(self.cfunc(*args))
        self.native_calls += 1
        return True, value
