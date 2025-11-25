import sys
from sqlglot import expressions as exp
from parser import parse_schema, parse_query
from encoder import encode
from sanity_checker import sanity_check
from z3 import *


def main():
    if len(sys.argv) != 4:
        exit("Usage: python main.py create-table.sql query1.sql query2.sql")
    schema_file, q1_file, q2_file = sys.argv[1], sys.argv[2], sys.argv[3]

    # parse the create table queries to get schema 
    global schema, not_null, null_funcs
    schema, not_null = parse_schema(schema_file) #e.g. Students: {'id': 'INT', 'name': 'STRING', 'age': 'INT'}

    print(f"schema: {schema}") # for debug use 
    print(f"not null attributes: {not_null}") # for debug use 

    # new added
    null_funcs = [Function("NullInt", IntSort(), BoolSort()), Function("NullString", StringSort(), BoolSort()),
                   Function("NullReal", RealSort(), BoolSort())]

    # parse each query
    q1_ast = parse_query(q1_file)
    q2_ast = parse_query(q2_file)
    # print_ast(schema, q1_ast, q2_ast) # for debug use

    q1_alias_map = build_alias_map(q1_ast)
    q2_alias_map = build_alias_map(q2_ast)
    print("q1_alias_map =", q1_alias_map) # for debug use
    print("q2_alias_map =", q2_alias_map) # for debug use

    # perform some cheap checks over the queries 
    sanity_check(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map)

    s = encode(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map, null_funcs, not_null)
    print(f"assertions: \n{s.assertions()}") # for debug use
    print(f"\nresult: {s.check()}")
    if s.check() == sat :
        # print(s.model())
        print_counterexample(schema, s.model())
    else :
        print("Query 1 and 2 are equivalent")


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
def print_counterexample(schema, model): 
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


if __name__ == "__main__":
    main()