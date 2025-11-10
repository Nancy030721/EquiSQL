import sys
from sqlglot import expressions as exp
from parser import parse_schema, parse_query
from z3 import *

def main():
    if len(sys.argv) != 4:
        exit("Usage: python main.py create-table.sql query1.sql query2.sql")
    schema_file, q1_file, q2_file = sys.argv[1], sys.argv[2], sys.argv[3]

    # parse schema and queries
    schema = parse_schema(schema_file) #e.g. Students: {'id': 'INT', 'name': 'STRING', 'age': 'INT'}
    q1_ast = parse_query(q1_file)
    q2_ast = parse_query(q2_file)
    print_ast(schema, q1_ast, q2_ast) # for debug use

    # perform some cheap checks over the queries 
    sanity_check(schema, q1_ast, q2_ast)

    encode_and_solve(schema, q1_ast, q2_ast)
     


def print_ast(schema, q1_ast, q2_ast) :
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

            else: #something else 
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
    for ast in [q1_ast, q2_ast]:
        # detech if queries contain operations that are not supported by our verifier 
        detect_unsupported(ast, i)

        for col in ast.find_all(exp.Column):
            table = col.table
            name = col.name
            # print(f"  {table}.{name}" if table else f"  {name}") # for debug use
            if table and table not in schema:
                exit(f"Unknown table: {table}")
            elif table and name not in schema[table]:
                print(f"Unknown column: {table}.{name}")
        i += 1




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

    # Outer joins
    for join in ast.find_all(exp.Join):
        # for now, let's just say join is not allowed
        unsupported.append("JOIN")
        # if join.side and join.side.lower() in {"left", "right", "full"}:
        #     unsupported.append(f"{join.side.upper()} JOIN")

    if len(unsupported) > 0: 
        exit(f"query {idx} contains operations that are not supported -- {unsupported}")




def encode_and_solve(schema, q1_ast, q2_ast):
    s = Solver()
    
    # step 1: declare variables for each query 
    vars_q1 = declare_variables(schema, q1_ast, idx="q1")
    vars_q2 = declare_variables(schema, q2_ast, idx="q2")
    
    # print("line147, vars_q1 =", vars_q1) # for debug use
    # print("line148, vars_q2 =", vars_q2) # for debug use

    # step 2: enforce that input tuples are the same 
    for table in schema:
        if table in vars_q1 and table in vars_q2:
            for col in schema[table]:
                s.add(vars_q1[table][col] == vars_q2[table][col])
  
    # step 3: add simple example constraints 
    # for now, just translate WHERE clause for comparison operators
    cond_q1 = encode_where_clause(q1_ast, vars_q1)
    cond_q2 = encode_where_clause(q2_ast, vars_q2)

    # step 4: ask -- is it possible that some variable makes q1 XOR q2
    q1_result = Bool("q1_result")
    q2_result = Bool("q2_result")
    s.add(q1_result == cond_q1)
    s.add(q2_result == cond_q2)
    s.add(q1_result != q2_result)
  
    print(f"\nresult: {s.check()}")
    if s.check() == sat :
        # print(s.model())
        print_counterexample(s.model())
    else :
        print("Query 1 and 2 are equivalent")


# for each table in both queries, declare Z3 variables for its columns
# returns a map, which maps  dict[table][column] -> Z3 variable
def declare_variables(schema, ast, idx):
    variables = {}

    # collect all table names used in both queries
    tables = set()
    for table in ast.find_all(exp.Table):
        tables.add(table.name)

    for table in tables:
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{idx}_{column}"
            if col_type == "INT":
                variables[table][column] = Int(var_name)
            else: # col_type = "STRING"
                variables[table][column] = String(var_name)

    return variables


# Adds constraints for simple WHERE clauses like 'age > 20' or 'id = 3'.
def encode_where_clause(ast, variables):
    where = ast.args.get("where")
    if not where:
        return BoolVal(True)

    expr = where.this
    return encode_condition(expr, variables)


def encode_condition(expr, variables):
    key = expr.key.lower()

    # for now, we're only handling simple comparisons: <, >, =, <=, >=
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
    else:
        print(f"Unsupported WHERE type: {key}")
        return BoolVal(True)



# convert a simple comparison expression to a Z3 constraint
def encode_comparison(left, right, op, variables):
    left_name = str(left).split(".")[-1] 
    right_val = str(right)

    # Try to resolve left operand
    for table_vars in variables.values():
        if left_name in table_vars:
            var = table_vars[left_name]
            break
   

    # Try to interpret right operand as int or string
    try:
        right_val = int(right_val)
    except ValueError:
        right_val = StringVal(right_val.strip("'\""))

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
    

# print an input tuple and the different behaviors q1 and q2 have on it
def print_counterexample(model): 
    # print(m)
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