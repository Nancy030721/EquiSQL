from z3 import *

# copied this program from the internet

# Declare integer variables
x = Int('x')
y = Int('y')

# Create a solver instance
s = Solver()

# Add constraints to the solver
s.add(x > 2)
s.add(y < 10)
s.add(x + 2*y == 7)

# Check for satisfiability
if s.check() == sat:
    # If satisfiable, print the model (solution)
    m = s.model()
    print(f"x = {m[x]}")
    print(f"y = {m[y]}")
else:
    print("No solution found.")