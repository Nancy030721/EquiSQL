import sys
from sqlglot import expressions as exp
from z3 import *


# perform some simple structural validation before logical reasoning --> fail fast if the inputs are incomparable
# including that
# 1.they project the same number of columns and names
# 2.they reference existing tables/columns
# 3.they reference the same set of tables
# 4.they have the same LIMIT and OFFSET 
def sanity_check(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map):
    def extract_select_cols(ast, idx):
        if (idx == 1):
            alias_map = q1_alias_map
        else :
            alias_map = q2_alias_map
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
                
            elif (expr.key== "star") :
                for table in alias_map.values() :
                    for col in schema[table]:
                        columns.append(col)
                
            else: # something else
                exit("not supported")
    
        return columns


    q1_cols = extract_select_cols(q1_ast, 1)
    q2_cols = extract_select_cols(q2_ast, 2)
    
    if q1_cols != q2_cols: # same column names
        err_message = (
            f"Queries returns different columns: Query1: {q1_cols} "
            f"vs Query 2: {q2_cols}."
        )
        exit(err_message)

    # check column exist in schema
    i = 1
    for ast in [q1_ast, q2_ast]:
        # detech if queries contain operations that are not supported by our verifier 
        detect_unsupported(ast, i)

        for col in ast.find_all(exp.Column):
            if (i == 1) :
                table = q1_alias_map[col.table]
            else :
                table = q2_alias_map[col.table]
                
            name = col.name
            if table and table not in schema:
                exit(f"Unknown table: {table}")
            elif table and name not in schema[table]:
                exit(f"Unknown column: {table}.{name}")
            elif not table:
                exit(f"Must specify the table for column {name}")
        
        i += 1

    if set(q1_alias_map.values()) != set(q2_alias_map.values()): #order doesn't matter
        err_message = (
            f"Queries do not reference the same set of tables: Query1: {q1_alias_map.values()} vs Query 2: {q2_alias_map.values()}."
        )
        exit(err_message)

    
    # check if LIMIT and OFFSET matches
    q1_offset, q1_limit, q2_offset, q2_limit = 0, 0, 0, 0
    if list(q1_ast.find_all(exp.Limit)):
        q1_offset = list(q1_ast.find_all(exp.Limit))[0]
        q1_offset = int(str(q1_offset.expression))
    if list(q2_ast.find_all(exp.Limit)):
        q2_offset = list(q2_ast.find_all(exp.Limit))[0]
        q2_offset = int(str(q2_offset.expression))
    if list(q1_ast.find_all(exp.Offset)):
        q1_offset = list(q1_ast.find_all(exp.Offset))[0]
    if list(q2_ast.find_all(exp.Offset)):
        q2_offset = list(q2_ast.find_all(exp.Offset))[0]
    
    if (q1_offset != q2_offset):
        err_message = (
            f"query1 skips the first {q1_offset} rows from the beginning of the result set, "
            f"while query2 skips the first {q2_offset} rows."
        )
        exit(err_message)
    if (q1_limit != q2_limit) :
        err_message = (
            f"query1 returns {q1_limit} rows at maximum while and query2 returns, while query2 skips the first {q2_limit}."
        )
        exit(err_message)



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


def exit(err_message):
    print(err_message)
    sys.exit(1)