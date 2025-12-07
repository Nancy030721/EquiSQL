import sys
from sqlglot import expressions as exp
from z3 import *


# perform some simple structural validation before logical reasoning --> fail fast if the inputs are incomparable
# including that
# 1.they project the same number of columns and names
# 2.they reference existing tables/columns
# 3.they reference the same set of tables
def sanity_check(schema, q1_ast, q2_ast, q1_alias_map, q2_alias_map):
    def normalize_aggregate(expr_str, alias_map):
        """Normalize aggregate expressions like SUM(S.age) -> SUM(age)"""
        expr_lower = expr_str.lower()
        # Handle patterns like sum(table.col) -> sum(col)
        for alias, table in alias_map.items():
            expr_lower = expr_lower.replace(f"{alias.lower()}.", "")
            expr_lower = expr_lower.replace(f"{table.lower()}.", "")
        return expr_lower

    def add_expr_to_column(expr, columns, alias_map):
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
                add_expr_to_column(inner_expr, columns)

        elif (expr.key== "star") :
            for table in alias_map.values() :
                for col in schema[table]:
                    columns.append(col)

        elif (expr.key in ["count", "sum", "avg"]):
            col_name = expr.args.get("this")
            normalized = normalize_aggregate(str(col_name), alias_map)
            columns.append(normalized)

        else: # something else
            exit(f"Expression type {expr.key} is not supported")



    def extract_select_cols(ast, idx):
        if (idx == 1):
            alias_map = q1_alias_map
        else :
            alias_map = q2_alias_map
        columns = []
        for expr in ast.expressions:
            add_expr_to_column(expr, columns, alias_map)

        return columns

    # for each query, build column --> tables map
    def build_col2tables(alias_map, schema):
        col2tables = {}
        for _, table in alias_map.items():     # alias: 'S' -> table: 'Students'
            for col in schema[table]:
                col2tables.setdefault(col, []).append(table)
        return col2tables


    q1_col2tables = build_col2tables(q1_alias_map, schema)
    q2_col2tables = build_col2tables(q2_alias_map, schema)
    q1_cols = extract_select_cols(q1_ast, 1)
    q2_cols = extract_select_cols(q2_ast, 2)


    # print(f"q1_cols = {q1_cols}")
    # print(f"q2_cols = {q2_cols}")

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
            if not col.table:
                if i == 1 :
                    cols2tables = q1_col2tables
                else :
                    cols2tables = q2_col2tables

                if col in cols2tables:
                    tables = cols2tables[col]
                    if len(tables) == 0:
                        exit(f"Column {col} is not found in any table")
                    elif len(tables) > 1:
                        exit(f"Column {col} appeared more than once in table {tables}, must specify which table it refers to")
                    # else: len(cols2tables[col]) > 1: doesn't do anything
            else:
                if i == 1 :
                    table = q1_alias_map[col.table]
                else :
                    table = q2_alias_map[col.table]

                name = col.name
                if table and table not in schema:
                    exit(f"Unknown table: {table}")
                elif table and name not in schema[table]:
                    exit(f"Unknown column: {table}.{name}")

        i += 1

    if set(q1_alias_map.values()) != set(q2_alias_map.values()): #order doesn't matter
        err_message = (
            f"Queries do not reference the same set of tables: Query1: {q1_alias_map.values()} vs Query 2: {q2_alias_map.values()}."
        )
        exit(err_message)

    if len(q1_alias_map.values()) > 2:
        exit("Only support equivalence check on at most two relations.")


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


    return q1_col2tables, q2_col2tables



def detect_unsupported(ast, idx):
    unsupported = []

    # GROUP BY and HAVING
    if list(ast.find_all(exp.Group)):
        unsupported.append("GROUP BY")
    if list(ast.find_all(exp.Having)):
        unsupported.append("HAVING")

    # Aggregation functions
    for f in list(ast.find_all(exp.Func)):
        if (f.key.lower() not in ["and", "or", "count", "sum", "avg"]) :
            unsupported.append("Aggregation functions")

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