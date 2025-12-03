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
    print_assertion = False
    if len(sys.argv) >= 5:
        if sys.argv[4].lower() == "-cvc5":
            solver_type = "cvc5" 
        print_assertion = sys.argv[4].lower() == "-a" or (len(sys.argv) > 5 and sys.argv[5].lower() == "-a")  

    print(f"Running equivalence check using SMT solver: {solver_type.upper()}")
    run_equivalence_check(sys.argv[1], sys.argv[2], sys.argv[3], solver_type, False, print_assertion)
    

def run_equivalence_check(schema_file, q1_file, q2_file, solver_type, test=False, print_assertion=False):
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
    # if not test:
    #     print_ast(schema, q1_ast, q2_ast) # for debug use

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

        if print_assertion:
            print("assertions:[")
            for a in s.assertions():
                print("  ", simplify(a)) # for debug use
                # print("  ", a) # for debug use
            print("]")
        

        print(f"\nresult: {result}")
        if s.check() == sat :
            # print(s.model())
            print_counterexample_z3(schema, s.model())
        else :
            print(f"Query 1 and 2 are equivalent, runtime: {end-start:.5f}s")

    else: #cvc5
        s, variables_to_interpret  = cvc5_encoder.encode(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map, not_null, primary_keys) 
        result = s.checkSat()
        if test:
            if result.isSat():
                return f"counterexample: {result}"
            return "EQUIVALENT"
        
        end = time.perf_counter()
        if print_assertion:
            print(f"assertions:") # for debug use, improved readability
            for assertion in s.getAssertions():
                print(assertion)
        print(f"\nresult: {result}")

        if result.isSat():
            model = s.getModel([], list(variables_to_interpret))
            model_str = model.decode("utf-8")
            print_counterexample_cvc5(schema, model_str)
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
    # # locator
    # print("----- Schema -----")
    # for table, cols in schema.items():
    #     print(f"{table}: {cols}")
    # print("----- End of Schema -----")

    print("\n------- Query 1 AST -----")
    print(repr(q1_ast))
    # print(q1_ast.sql(pretty=True))
    # print(q1_ast.dump())

    # print("\n------- Query 2 AST -----")
    # print(repr(q2_ast))



def print_counterexample_z3(schema, model): 
    valuation = {d.name(): model[d] for d in model.decls()}

    print("\n===== COUNTEREXAMPLE FOUND =====")

    # Print the base tables
    print("\n----- Base Table Rows -----")
    for table, attributes in schema.items():
        row_data = {attr: valuation.get(f"{table}_q1_{attr}", 'NULL')
                    for attr in attributes}
        print(f"{table}: {row_data}")

    # Show the query results and interpret them
    q1_result = valuation.get("q1_result", None)
    q2_result = valuation.get("q2_result", None)
    
    print("\n----- Query Results Interpretation -----")
    if q1_result is not None:
        print(f"Query 1 Result: {'Condition met' if q1_result else 'Condition not met'}")

    if q2_result is not None:
        print(f"Query 2 Result: {'Condition met' if q2_result else 'Condition not met'}")

    print("\n----- Raw Model -----")
    print(model)

    print("\n==========================================")



def print_counterexample_cvc5(schema, model_str):
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
        for col, _ in cols.items():
            q1_const_name = f"{table}_{'q1'}_{col}"  
            q2_const_name = f"{table}_{'q2'}_{col}"  
            q1_const_val = values.get(q1_const_name)
            q2_const_val = values.get(q2_const_name)
            if q1_const_val != q2_const_val:
                exit("Query 1 and 2 takes different input, this should never happen")
            row_terms.append(f"{col.lower()}={q1_const_val}")

        print(f"Table {table}: ({', '.join(row_terms)})")

    q1 = values.get("q1_result").lower() == "true"
    q2 = values.get("q2_result").lower() == "true"
    
    print(f"line180 in main.py, q1_result = {values.get('q1_result')}, q2_result = {values.get('q2_result')}")


    print("\nInterpretation:")
    if q1 and not q2:
        print("  -> Query 1 returned a row, Query 2 did not.")
    elif q2 and not q1:
        print("  -> Query 2 returned a row, Query 1 did not.")
    # these branches should never be reached
    elif q1 and q2:
        exit("  -> Both queries returned a row, what happened???")
    else: 
        exit("  -> Both queries returned nothing, what happened???")



if __name__ == "__main__":
    main()