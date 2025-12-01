import sys
from sqlglot import expressions as exp
from parser import parse_schema, parse_query
from sanity_checker import sanity_check
import z3_encoder
from z3 import *
import cvc5_encoder
from cvc5 import *
import time


def main():
    if len(sys.argv) < 4:
        exit("Usage: python main.py create-table.sql query1.sql query2.sql (optional -z3 or -cvc5)")
    solver_type = "z3" #z3 as default
    if len(sys.argv) == 5:
        if sys.argv[4] == "-cvc5":
            solver_type = "cvc5" 
    print(f"Running equivalence check using SMT solver: {solver_type.upper()}")
    run_equivalence_check(sys.argv[1], sys.argv[2], sys.argv[3], solver_type)
    

def run_equivalence_check(schema_file, q1_file, q2_file, solver_type, test=False):
    # start timing
    start = time.perf_counter()

    # parse the create table queries to get schema 
    global schema, null_funcs
    schema, not_null, primary_keys = parse_schema(schema_file) #e.g. Students: {'id': 'INT', 'name': 'STRING', 'age': 'INT'}

    if not test: 
        print(f"schema: {schema}") # for debug use
        print(f"primary keys: {primary_keys}") # for debug use 
        print(f"not null attributes: {not_null}") # for debug use 

    # parse each query
    q1_ast = parse_query(q1_file)
    q2_ast = parse_query(q2_file)
    # print_ast(schema, q1_ast, q2_ast) # for debug use

    q1_alias_map = build_alias_map(q1_ast)
    q2_alias_map = build_alias_map(q2_ast)
    # print("q1_alias_map =", q1_alias_map) # for debug use
    # print("q2_alias_map =", q2_alias_map) # for debug use

    # perform some cheap checks over the queries 
    sanity_check(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map)


    if solver_type == "z3":
        s = z3_encoder.encode(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map, not_null, primary_keys)
        result = s.check()
        
        if test:
            if result == sat:
                return f"counterexample: {s.check()}"
            return "EQUIVALENT"
    
        end = time.perf_counter()
        print(f"assertions: \n{s.assertions()}") # for debug use
        print(f"\nresult: {result}")
        if s.check() == sat :
            # print(s.model())
            print_counterexample_z3(schema, s.model())
        else :
            print(f"Query 1 and 2 are equivalent, runtime: {end-start:.5f}s")

    else: #cvc5
        s, variables_to_interpret = cvc5_encoder.encode(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map, not_null, primary_keys) 
        result = s.checkSat()
        if test:
            if result.isSat():
                return f"counterexample: {result}"
            return "EQUIVALENT"
        
        end = time.perf_counter()
        print(f"assertions: \n{s.getAssertions()}") # for debug use
        print(f"\nresult: {result}")

        if result.isSat():
            model = s.getModel([], list(variables_to_interpret))
            model_str = model.decode("utf-8")
            print_counterexample_cvc5(schema, model_str, 1)
        else :
            print(f"Query 1 and 2 are equivalent, runtime: {end-start:.5f}s")



def build_alias_map(ast):
    alias_map = {}
    for tbl in ast.find_all(exp.Table):
        real = tbl.name  # real table name as string

        alias_expr = tbl.args.get("alias")
        if alias_expr:
            alias = alias_expr.name  # alias string
            alias_map[alias] = real
        else:
            alias_map[real] = real

    return alias_map


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


# print an input tuple and the different behaviors q1 and q2 have on it
def print_counterexample_z3(schema, model): 
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
        if table in schema.keys():
            attrs_str = ", ".join(f"{k}={v}" for k, v in cols.items())
            print(f"Table {table}: ({attrs_str})")


    print("Interpretation:")
    if q1_result and not q2_result:
        print("  -> Query 1 returns the tuple while Query 2 does not.")
    elif q2_result and not q1_result:
        print("  -> Query 2 returns the tuple while Query 1 does not.")
    else:
        print("  -> No difference in outputs (Whoops???).")


def print_counterexample_cvc5(schema, model_str, idx):
    values = {}
    for line in model_str.split("\n"):
        line = line.strip()
        if line.startswith("(define-fun"):
            parts = line.replace("(", "").replace(")", "").split()
            name = parts[1]
            value = parts[-1]
            values[name] = value

    print("\nCounterexample:\n")

    for table, cols in schema.items():
        row_terms = []
        for col, col_type in cols.items():
            const_name = f"{table}__{col}"
            if const_name not in values:
                const_name = f"{table}_{'q1' if idx==1 else 'q2'}_{col}"  
            val = values.get(const_name)
            row_terms.append(f"{col.lower()}={val}")

        print(f"Table {table}: ({', '.join(row_terms)})")

    q1 = values.get("q1_result", "false").lower() == "true"
    q2 = values.get("q2_result", "false").lower() == "true"

    print("\nInterpretation:")
    if q1 and not q2:
        print("  -> Query 1 returned a row, Query 2 did not.")
    elif q2 and not q1:
        print("  -> Query 2 returned a row, Query 1 did not.")
    elif q1 and q2:
        print("  -> Both queries returned a row, what happened???")
    else: 
        print("  -> Both queries didn't return a row, what happened???")



if __name__ == "__main__":
    main()