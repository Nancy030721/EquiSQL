import sys
from sqlglot import expressions as exp
from parser import parse_schema, parse_query
from z3 import *


# 
def main():
    if len(sys.argv) != 4:
        exit("Usage: python main.py create-table.sql query1.sql query2.sql")
    schema_file, q1_file, q2_file = sys.argv[1], sys.argv[2], sys.argv[3]

    # define and initialize global variables
    global NULL
    NULL = IntVal(-1)

    # parse the create table queries to get schema 
    global schema
    schema = parse_schema(schema_file) #e.g. Students: {'id': 'INT', 'name': 'STRING', 'age': 'INT'}

    # parse each query
    q1_ast = parse_query(q1_file)
    q2_ast = parse_query(q2_file)
    print_ast(schema, q1_ast, q2_ast) # for debug use

    # perform some cheap checks over the queries 
    sanity_check(schema, q1_ast, q2_ast)
    encode_and_solve(schema, q1_ast, q2_ast)
     


def print_ast(schema, q1_ast, q2_ast) :
    # locator
    print("----- Schema -----")
    for table, cols in schema.items():
        print(f"{table}: {cols}")
    print("----- End of Schema -----")

    # print("\n----- Query 1 AST -----") 
    # print(repr(q1_ast))
    # # print(q1_ast.sql(pretty=True))
    # # print(q1_ast.dump())
    
    # print("\n----- Query 2 AST -----")
    # print(repr(q2_ast))



# perform some simple structural validation before logical reasoning --> fail fast if the inputs are incomparable
# including that
# 1.they project the same number of columns and names
# 2.they reference existing tables/columns
# 3.they reference the same set of tables
def sanity_check(schema, q1_ast, q2_ast):

    def extract_select_cols(ast):
        columns = []
        for expr in ast.expressions: 
            if expr.key == "column": 
                col_name = expr.args.get("this")
                if col_name:
                    columns.append(str(col_name))

            elif expr.key == "alias":
                alias_id = expr.args.get("alias")
                inner_expr = expr.args.get("this")
                if alias_id:
                    columns.append(str(alias_id))
                else:
                    columns.append(str(inner_expr))

            else: #something else, like "select *"
                exit("not supported")
    
        return columns

    q1_cols = extract_select_cols(q1_ast)
    q2_cols = extract_select_cols(q2_ast)

    if len(q1_cols) != len(q2_cols): # same column number
        exit("Queries project different numbers of columns:", len(q1_cols), "vs", len(q2_cols))

    if set(q1_cols) != set(q2_cols): # same column names
        err_message = "Queries project different column names:" , q1_cols, "vs", q2_cols
        exit(err_message)

    
    # check column exist in schema
    i = 1
    q1_tables = set()
    q2_tables = set()

    for ast in [q1_ast, q2_ast]:
        # detech if queries contain operations that are not supported by our verifier 
        detect_unsupported(ast, i)

        for col in ast.find_all(exp.Column):
            table = col.table
            name = col.name
            if (i == 1) :
                q1_tables.add(table)
            else :
                q2_tables.add(table)
            # print(f"  {table}.{name}" if table else f"  {name}") # for debug use
            if table and table not in schema:
                exit(f"Unknown table: {table}")
            elif table and name not in schema[table]:
                exit(f"Unknown column: {table}.{name}")
        
        i += 1

    if (q1_tables != q2_tables) :
        exit("quey1 and query2 do not reference the same set of tables")




# todo: refine this, I think it will be easier and more complete to state
# what we support rather than what we don't support
def detect_unsupported(ast, idx):
    unsupported = []

    # GROUP BY and HAVING
    if list(ast.find_all(exp.Group)):
        unsupported.append("GROUP BY")
    if list(ast.find_all(exp.Having)):
        unsupported.append("HAVING")

    # Aggregation functions
    for f in list(ast.find_all(exp.Func)):
        if (f.key.lower() not in ["and", "or"]) :
            unsupported.append("Aggregation functions")

    # DISTINCT
    if ast.args.get("distinct"):
        unsupported.append("DISTINCT")

    # UNION / INTERSECT / EXCEPT
    if list(ast.find_all(exp.Union)):
        unsupported.append("UNION / INTERSECT / EXCEPT")

    # Subqueries / EXISTS / IN (with SELECT)
    if list(ast.find_all(exp.Subquery)):
        unsupported.append("Subqueries (EXISTS/IN/SELECT in WHERE)")

    # ORDER BY
    if list(ast.find_all(exp.Order)):
        unsupported.append("ORDER BY")

    if len(unsupported) > 0: 
        exit(f"query {idx} contains operations that are not supported -- {unsupported}")




def encode_and_solve(schema, q1_ast, q2_ast):
    global s
    s = Solver()
    
    # step 1: declare variables for each query 
    vars_q1 = declare_variables(schema, q1_ast, idx="q1")
    vars_q2 = declare_variables(schema, q2_ast, idx="q2")

    # step 2: enforce that input tuples are the same 
    for table in schema:
        if table in vars_q1 and table in vars_q2:
            for col in schema[table]:
                s.add(vars_q1[table][col] == vars_q2[table][col])
 
    # step 3: add simple example constraints 
    cond_q1 = encode_query(q1_ast, vars_q1)
    cond_q2 = encode_query(q2_ast, vars_q2)

    # print("encoding for query1:", cond_q1) # for debug use
    # print("encoding for query2:", cond_q2) # for debug use

    # step 4: ask -- is it possible that some variable makes q1 XOR q2
    q1_result = Bool("q1_result")
    q2_result = Bool("q2_result")
    s.add(q1_result == cond_q1)
    s.add(q2_result == cond_q2)
    s.add(q1_result != q2_result)
   
    print(f"assertions: \n{s.assertions()}") # for debug use
    print(f"\nresult: {s.check()}")
    if s.check() == sat :
        # print(s.model())
        print_counterexample(s.model())
    else :
        print("Query 1 and 2 are equivalent")


# for each table in both queries, declare Z3 variables for its columns
# returns a map, which maps dict[table][column] -> Z3 variable
def declare_variables(schema, ast, idx):
    variables = {}
    variables["row_identity"] = {}

    # collect all table names used in the query
    tables = set()
    for table in ast.find_all(exp.Table):
        tables.add(table.name)
        # synthetic row identity
        variables["row_identity"][table.name] = Int(f"{table.name}_row")

    for table in tables:
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{idx}_{column}"
            if col_type == "INT":
                variables[table][column] = Int(var_name)
            elif col_type =="STRING":
                variables[table][column] = String(var_name)
            else: #col_type == "REAL"
                variables[table][column] = Real(var_name)

    return variables


def encode_query(ast, variables):
    cond_join = encode_join_clause(ast, variables)
    cond_where = encode_where_clause(ast, variables)
    return And(cond_join, cond_where)

# add constraints for inner join like 'FROM T1 JOIN T2 ON T1.id = T2.id'.
def encode_join_clause(ast, variables):
    joins = ast.args.get("joins")
    # if there's no (explicit) joins
    if not joins or (len(joins) == 1 and (joins[0].args.get("on")) is None): 
        return BoolVal(True)
    
    
    left_table_name = str(ast.args.get("from").args["this"])
    encoding = True
    
    global left_join_func, right_join_func, full_join_func
    left_join_func = Function("left_join_func", IntSort(), IntSort(), BoolSort())
    right_join_func = Function("right_join_func", IntSort(), IntSort(), BoolSort())
    full_join_func = Function('full_join_func', IntSort(), IntSort(), BoolSort())

    for i in range(len(joins)) :
        join = joins[i]
        cond = join.args.get("on")
        encoded_cond = encode_condition(cond, variables)
        right_table_name = str(join.args["this"])
        # print(f"line228, right_table_name = {right_table_name}")
        if (not join.side): # inner join
            # for inner loop, it doesn't matter if the condition is placed in ON or WHERE clause 
            # since we always use AND to connect them.
            temp = encoded_cond    
        else: # outer join
            side = join.side.lower()
            left_row = variables["row_identity"][left_table_name]
            right_row = variables["row_identity"][right_table_name]  

            if (side == "left") :
                temp = encode_left_join(encoded_cond, left_row, right_row)
            elif (side == "right") :
                temp = encode_right_join(encoded_cond, left_row, right_row)
            elif (side == "full") :
                temp = encode_full_join(encoded_cond, left_row, right_row)
            else:
                exit(f"unknown join type: {side.upper()} JOIN")
        
        encoding = And(temp, encoding)
        
    return encoding


# todo: there are likely something wrong in encode_left_join and encode_right_join
# use command:
# python main.py test/create-table.sql test/join/left_join3.sql test/join/right_join2.sql
# expected: unsat/EQUIVALENT
# actual: counterexample
def encode_left_join(on_pred, left_row, right_row):
    global NULL, s, left_join_func, right_join_func
    s.add(left_join_func(left_row, right_row) == right_join_func(right_row, left_row))
    return And(
        Implies(on_pred, left_join_func(left_row, right_row)),   # match -> include (A,B)
        Implies(Not(on_pred), left_join_func(left_row, NULL)),  # no match -> include (A,NULL)
        Implies(left_join_func(left_row, right_row), on_pred)      # for safety, if (A,B) appears -> must match
    )


# todo: 
def encode_right_join(on_pred, left_row, right_row):
    global NULL, s, left_join_func, right_join_func
    s.add(left_join_func(left_row, right_row) == right_join_func(right_row, left_row))
    return And(
        Implies(on_pred, right_join_func(left_row, right_row)),   # match -> include (A,B)
        Implies(Not(on_pred), right_join_func(NULL, right_row)),  # no match -> include (NULL,B)
        Implies(right_join_func(left_row, right_row), on_pred)      # for safety, if (A,B) appears -> must match
    )


def encode_full_join(on_pred, left_row, right_row):
    global NULL, s, full_join_func
    s.add(full_join_func(left_row, right_row) == full_join_func(right_row, left_row))
    return And(
        Implies(on_pred, full_join_func(left_row, right_row)),   # match -> include (A,B)
        Implies(Not(on_pred), And(full_join_func(NULL, right_row), full_join_func(left_row, NULL))),  # no match -> include (NULL,B)
        Implies(full_join_func(left_row, right_row), on_pred)      # for safety, if (A,B) appears -> must match
    )
    

# add constraints for simple WHERE clauses like 'R.age > 20' or 'T.id = 3'.
def encode_where_clause(ast, variables):
    where = ast.args.get("where")
    if not where:
        return BoolVal(True)

    expr = where.this
    return encode_condition(expr, variables)


def encode_condition(expr, variables):
    key = expr.key.lower()

    # for now, we're only handling simple comparisons: <, >, =, <=, >=
    # and, or, not
    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(left, right, key, variables)
            if constraint is not None:
                # print(f"Added constraint: {constraint}") #for debug use
                return constraint
        elif key == "and":
            return And(encode_condition(expr.args["this"], variables),
                   encode_condition(expr.args["expression"], variables))
        elif key == "or":
            return Or(encode_condition(expr.args["this"], variables),
                   encode_condition(expr.args["expression"], variables))   
        elif key == "not":
            return Not(encode_condition(expr.args["this"], variables))

    exit(f"Unsupported type: {key}")



# convert a simple comparison expression to a Z3 constraint
def encode_comparison(left, right, op, variables):
    # print(f"line306, left = {left}, right = {right}")
    var, _ = encode_expr(left, variables)
    right_val, _ = encode_expr(right, variables)

    if op == "gt":
        return var > right_val
    elif op == "lt":
        return var < right_val
    elif op == "gte":
        return var >= right_val
    elif op == "lte":
        return var <= right_val
    elif op == "eq":
        return var == right_val
    else:
        return None


def encode_expr(expr, variables):
    # print("line324, expr=", expr, ", type =", type(expr))
    # literals
    if isinstance(expr, exp.Literal):
        if expr.is_int or expr.is_number:
            return IntVal(int(str(expr))), "INT"
        if expr.is_string:
            return StringVal(expr.this), "STRING"
        # fall back
        s = str(expr).strip("'\"")
        return IntVal(int(s)) if s.isdigit() else StringVal(s)
    

    if isinstance(expr, exp.Condition):
        key = expr.key.lower()
        # handle math ops
        if key in ["add", "sub", "mul"]:
            left, right = expr.args["this"], expr.args["expression"]
            print(f"line343, left = {left}, right = {right}")
            left, left_type = encode_expr(left, variables)
            right, right_type = encode_expr(right, variables)
            
            if (left_type == "STRING" or right_type == "STRING"):
                exit("cannot perform arithematic operation on String type")
            if (left_type != right_type):
                exit(f"type mistach between {left_type} and {right_type}")

            if key == "add":
                return left + right, left_type
            elif key == "sub":
                return left - right, left_type
            elif key == "mul":
                return left * right, left_type
            else:
                raise ValueError(f"Unsupported math operation {key}")
   
    if isinstance(expr, exp.Column):
        table = str(expr.table)
        column = str(expr.this)
        if table in variables.keys(): 
            if column in variables[table]:
                return variables[table][column], schema[table][column]
        exit(f"attribute not found: {expr}")
    
    exit(f"encode_expr: could not resolve {expr}")



# print an input tuple and the different behaviors q1 and q2 have on it
def print_counterexample(model): 
    q1_result = model.evaluate(Bool("q1_result"), model_completion=True)
    q2_result = model.evaluate(Bool("q2_result"), model_completion=True)

    # group values by table and query index
    tuples = {}
    for d in model.decls():
        name = d.name()
        val = model[d]

        if name.lower() in ["q1_result", "q2_result"]:
            continue

        parts = name.split("_")
        if len(parts) < 3:
            continue

        table = parts[0]
        col = "_".join(parts[2:])  # skip Q1/Q2 middle part

        tuples.setdefault(table, {})[col] = val # we only keep one entry per table.column

    # todo: need to edit line433-435 a bit for Z3.Function
    for table, cols in tuples.items():
        attrs_str = ", ".join(f"{k}={v}" for k, v in cols.items())
        print(f"Table {table}: ({attrs_str})")

   
    print("Interpretation:")
    if q1_result and not q2_result:
        print("  -> Query 1 returns the tuple while Query 2 does not.")
    elif q2_result and not q1_result:
        print("  -> Query 2 returns the tuple while Query 1 does not.")
    else:
        print("  -> No difference in outputs (Whoops???).")
   

def exit(err_message):
    print(err_message)
    sys.exit(1)


if __name__ == "__main__":
    main()