"""この章で使える構文だけを使った、小さな実行例。"""
from frontend import parse_program
from interpreter import Interpreter


source = 'let price=80; let total=100+price*3; if total { total=total-40; print total; } else { print 0; }'
result = Interpreter(parse_program(source)).run()
print(result.output)
print(result.globals)
