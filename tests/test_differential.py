"""乱数の種を固定し、異なる実行方法の意味を比べる。"""
import random
import unittest
from frontend import parse_program
from interpreter import Interpreter
from bytecode import compile_program
from vm import VM
from optimizer import optimize_program


class DifferentialTests(unittest.TestCase):
    def test_generated_integer_expressions(self):
        randomizer = random.Random(20261101)
        def expression(depth):
            if depth == 0 or randomizer.randrange(4) == 0:
                return randomizer.choice(['x', 'y', str(randomizer.randint(-9, 9))])
            if randomizer.randrange(5) == 0:
                return '-(' + expression(depth - 1) + ')'
            left = expression(depth - 1)
            right = expression(depth - 1)
            op = randomizer.choice(['+', '-', '*', '<', '<=', '>', '>=', '==', '!='])
            return '(' + left + op + right + ')'
        values = [0, 1, -1, 2**63-1, -2**63, 2**70]
        for _ in range(120):
            source = ('fn f(x,y) { return ' + expression(4) + '; } print f('
                      + str(randomizer.choice(values)) + ','
                      + str(randomizer.choice(values)) + ');')
            with self.subTest(source=source):
                program = parse_program(source)
                expected = Interpreter(program).run()
                direct = VM(compile_program(program)).run()
                changed = VM(compile_program(optimize_program(program))).run()
                self.assertEqual(expected.output, direct.output)
                self.assertEqual(expected.output, changed.output)
                self.assertEqual(expected.globals, changed.globals)


if __name__ == '__main__':
    unittest.main()
