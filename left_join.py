# suppose we want to check if the following two queries are equivalent:
# query1: 
    # SELECT A.name
    # FROM A 
    # LEFT JOIN B ON A.id = B.id;
# query2:
    # SELECT A.name
    # FROM A 
    # JOIN B ON A.id = B.id;
# we are supposed to see sat, followed by a counterexample 


from z3 import *

# declare variables for q1
A_q1_id = Int('A_q1_id')
A_q1_name = String('A_q1_name')
B_q1_id = Int('B_q1_id')
B_q1_name = String('B_q1_name')
# declare variables for q2
A_q2_id = Int('A_q2_id')
A_q2_name = String('A_q2_name')
B_q2_id = Int('B_q2_id')
B_q2_name = String('B_q2_name')
# define what NULL is 
NULL = IntVal(-1) 
# actually no matter which value I choose, there are always other values that are not equal to it
# which helps distinguish OUTER JOIN from INNER JOIN

# initialize solver, 
# and add constraints on that the inputs for q1 and q2 are equal. 
s = Solver()
s.add(A_q1_id == A_q2_id)
s.add(A_q1_name == A_q2_name)
s.add(B_q1_id == B_q2_id)
s.add(B_q1_name == B_q2_name)

# encode q1
cond_q1 = And(True, A_q1_id == B_q1_id) # the first True comes from "no explicit join"
# done 

# encode q2
LeftJoin_int = Function('LeftJoin', IntSort(), IntSort(), BoolSort())
# LeftJoin_string = Function('LeftJoin', StringSort(), StringSort(), BoolSort())
# LeftJoin_real = Function('LeftJoin', RealSort(), RealSort(), BoolSort())
# 1) matching pairs
cond_q2 = Implies(A_q2_id == B_q2_id, LeftJoin_int(A_q2_id, B_q2_id))
# 2) unmatched A: output (A, NULL)
cond_q2 = And(cond_q2, Implies(A_q2_id != B_q2_id, LeftJoin_int(A_q2_id, NULL)))
# during real encoding process, will need to choose function based on the type 
# e.g. if we perform left join on A.name = B.name, then use LeftJoin_string
# done

q1_result = Bool("q1_result")
q2_result = Bool("q2_result")
s.add(q1_result == cond_q1)
s.add(q2_result == cond_q2)
s.add(q1_result != q2_result)


print(s.check())
print(s.model())


# output:
# sat
# [A_q2_id = 0,
#  B_q2_id = 1,
#  q1_result = False,
#  B_q2_name = "",
#  B_q1_name = "",
#  A_q2_name = "",
#  A_q1_name = "",
#  A_q1_id = 0,
#  B_q1_id = 1,
#  q2_result = True,
#  LeftJoin = [(0, -1) -> True, else -> False]]

# interpretation:
# When table A has a tuple (0, ""), and B has (1, "")
# q1 will not return it, while q2 does.