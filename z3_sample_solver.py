# copied this program from the official Z3 tutorial
from z3 import *

x, y = Ints('x y')
f = Function('f', IntSort(), IntSort())
s = Solver()
s.add(f(f(x)) == x, f(x) == y, x != y)
print(s.check())
print(s.model())



# # used for experimenting some ideas
# from z3 import *