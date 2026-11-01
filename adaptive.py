"""Call-entry tiering and guarded constants, not frame deoptimization or OSR."""
from collections import Counter, defaultdict

from bytecode import compile_program
from native import NativeFunction, UnsupportedNative, NativeUnavailable, MIN_INT, MAX_INT
from vm import VM


class AdaptiveRuntime:
    def __init__(self, program, threshold=8, profile_threshold=32):
        if type(threshold) is not int or threshold < 1:
            raise ValueError("thresholdは1以上の整数が必要です")
        if type(profile_threshold) is not int or profile_threshold < 1:
            raise ValueError("profile_thresholdは1以上の整数が必要です")
        self.program = program
        self.threshold = threshold
        self.profile_threshold = profile_threshold
        self.calls = Counter()
        self.profiles = defaultdict(Counter)
        self.compilations = 0
        self.native_hits = 0
        self.guard_misses = 0
        self.fallbacks = 0
        self.general = {}
        self.specialized = {}
        self.unavailable = {}
        self.vm = VM(compile_program(program), hook=self.hook)

    def maybe_compile(self, name):
        function = self.program.functions.get(name)
        if function is None or name in self.unavailable:
            return
        if self.calls[name] >= self.threshold and name not in self.general:
            try:
                self.general[name] = NativeFunction(function)
            except (UnsupportedNative, NativeUnavailable) as error:
                self.unavailable[name] = str(error)
                return
            self.compilations += 1
        if name not in self.general or self.calls[name] < self.profile_threshold:
            return
        if not function.params or not self.profiles[name]:
            return
        value, count = self.profiles[name].most_common(1)[0]
        if count * 5 < self.calls[name] * 4:
            return
        constants = {function.params[0]: value}
        old = self.specialized.get(name)
        if old is not None and old.constants == constants:
            return
        try:
            specialized = NativeFunction(function, constants)
        except (UnsupportedNative, NativeUnavailable):
            return
        self.specialized[name] = specialized
        self.compilations += 1

    def hook(self, name, args, fallback):
        self.calls[name] += 1
        if args and type(args[0]) is int and MIN_INT <= args[0] <= MAX_INT:
            self.profiles[name][args[0]] += 1
        self.maybe_compile(name)
        specialized = self.specialized.get(name)
        if specialized is not None:
            expected = specialized.constants[specialized.params[0]]
            if not args or args[0] != expected:
                self.guard_misses += 1
            else:
                ok, value = specialized.try_call(args)
                if ok:
                    self.native_hits += 1
                    return value
        general = self.general.get(name)
        if general is not None:
            ok, value = general.try_call(args)
            if ok:
                self.native_hits += 1
                return value
        self.fallbacks += 1
        return fallback()

    def run(self):
        return self.vm.run()
