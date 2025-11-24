import sys
from sqlglot import expressions as exp
from parser import parse_schema, parse_query
from z3 import *


def main():
    if len(sys.argv) != 4:
        exit("Usage: python main.py create-table.sql query1.sql query2.sql")
    schema_file, q1_file, q2_file = sys.argv[1], sys.argv[2], sys.argv[3]

    # define and initialize global variables
    global NULL, q1_alias_map, q2_alias_map
    NULL = IntVal(-1)

    # parse the create table queries to get schema
    global schema
    schema = parse_schema(schema_file) #e.g. Students: {'id': 'INT', 'name': 'STRING', 'age': 'INT'}

    # parse each query
    q1_ast = parse_query(q1_file)
    q2_ast = parse_query(q2_file)
    print_ast(schema, q1_ast, q2_ast) # for debug use


    q1_alias_map = build_alias_map(q1_ast)
    q2_alias_map = build_alias_map(q2_ast)
    print("q1_alias_map=", q1_alias_map) # for debug use
    print("q2_alias_map=", q2_alias_map) # for debug use

    # perform some cheap checks over the queries
    sanity_check(schema, q1_ast, q2_ast)
    encode_and_solve(schema, q1_ast, q2_ast)


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



# perform some simple structural validation before logical reasoning --> fail fast if the inputs are incomparable
# including that
# 1.they project the same number of columns and names
# 2.they reference existing tables/columns
# 3.they reference the same set of tables
def sanity_check(schema, q1_ast, q2_ast):
    global q1_alias_map, q2_alias_map

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
    q2_cols = extract_select_cols(q2_ast, 1)

    if len(q1_cols) != len(q2_cols): # same column number
        exit("Queries project different numbers of columns:", len(q1_cols), "vs", len(q2_cols))

    if set(q1_cols) != set(q2_cols): # same column names
        err_message = "Queries project different column names: Query1:" , q1_cols, "vs Query 2:", q2_cols
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

    if set(q1_alias_map.values()) != set(q2_alias_map.values()):
        print("line135:", set(q1_alias_map.values()))
        print("line136:", set(q2_alias_map.values()))
        exit("query1 and query2 do not reference the same set of tables")


# todo: lower priority, works fine at least for good cases,
# but refinement needed -- I think it will be easier and more complete to state
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
    global s, q1_alias_map, q2_alias_map
    s = Solver()

    # step 1: declare variables for each query
    vars_q1 = declare_variables(schema, idx=1)
    vars_q2 = declare_variables(schema, idx=2)


    # step 2: enforce that input tuples are the same
    for table in schema:
        if table in q1_alias_map.values() and table in q2_alias_map.values():
            for col in schema[table]:
                s.add(vars_q1[table][col] == vars_q2[table][col])

    # step 3: add simple example constraints
    cond_q1 = encode_query(q1_ast, 1, vars_q1)
    cond_q2 = encode_query(q2_ast, 2, vars_q2)

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
def declare_variables(schema, idx):
    global q1_alias_map, q2_alias_map

    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map
    variables = {}
    variables["row_identity"] = {}

    # synthetic row identity - use real table names (not aliases) for consistency
    # This ensures that the same table uses the same row_identity variable across queries
    for alias, real_table in alias_map.items():
        if real_table not in variables["row_identity"]:
            variables["row_identity"][real_table] = Int(f"{real_table}_row")
        # Also store mapping from alias to real table for easy lookup
        variables["row_identity"][alias] = variables["row_identity"][real_table]

    for table in alias_map.values():
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{idx}_{column}"
            if col_type == "INT":
                variables[table][column] = Int(var_name)
            elif col_type =="STRING":
                variables[table][column] = String(var_name)
            else: #col_type == "REAL"
                variables[table][column] = Real(var_name)

    if (idx == 1) :
        q1_alias_map = alias_map
    else :
        q2_alias_map = alias_map

    return variables


def encode_query(ast, idx, variables):
    # Check if WHERE clause filters on the "other side" of outer joins
    # This effectively converts outer joins to inner joins
    where = ast.args.get("where")
    if where:
        # Extract tables referenced in WHERE clause
        where_tables = extract_tables_from_condition(where.this, idx)
        # Modify join encoding if WHERE filters on other side
        cond_join = encode_join_clause(ast, idx, variables, where_tables)
    else:
        cond_join = encode_join_clause(ast, idx, variables, set())
    cond_where = encode_where_clause(ast, idx, variables)
    return And(cond_join, cond_where)

# Extract tables referenced in a condition expression
def extract_tables_from_condition(expr, idx):
    global q1_alias_map, q2_alias_map
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map

    tables = set()

    if isinstance(expr, exp.Column):
        table = alias_map.get(str(expr.table), str(expr.table))
        tables.add(table)
    elif isinstance(expr, exp.Condition):
        key = expr.key.lower()
        if key in ["gt", "lt", "gte", "lte", "eq", "is"]:
            left = expr.args.get("this")
            right = expr.args.get("expression")
            if left:
                tables.update(extract_tables_from_condition(left, idx))
            if right:
                tables.update(extract_tables_from_condition(right, idx))
        elif key in ["and", "or"]:
            tables.update(extract_tables_from_condition(expr.args["this"], idx))
            tables.update(extract_tables_from_condition(expr.args["expression"], idx))
        elif key == "not":
            tables.update(extract_tables_from_condition(expr.args["this"], idx))

    return tables

# add constraints for inner join like 'FROM T1 JOIN T2 ON T1.id = T2.id'.
# todo: some bug here
def encode_join_clause(ast, idx, variables, where_tables=None):
    global q1_alias_map, q2_alias_map
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map

    if where_tables is None:
        where_tables = set()

    joins = ast.args.get("joins")
    # if there's no (explicit) joins
    if not joins or (len(joins) == 1 and (joins[0].args.get("on")) is None):
        return BoolVal(True)

    # Extract left table from FROM clause - handle different AST structures
    from_clause = ast.args.get("from")
    left_table_name = None

    if from_clause is not None:
        # Handle different structures: Table directly, or nested in args["this"]
        if isinstance(from_clause, exp.Table):
            left_table_name = from_clause.name
        elif hasattr(from_clause, 'args') and from_clause.args.get("this"):
            if isinstance(from_clause.args["this"], exp.Table):
                left_table_name = from_clause.args["this"].name
            else:
                # Try to extract from nested structure
                left_table_name = from_clause.args["this"].name if hasattr(from_clause.args["this"], 'name') else None

    # If FROM is None or we couldn't extract the table, try to get it from the first table in alias_map
    # This can happen when sqlglot structures explicit joins differently
    if left_table_name is None:
        # Get the first table from alias_map - this should be the leftmost table
        tables_in_order = list(alias_map.keys())
        if tables_in_order:
            left_table_name = tables_in_order[0]
        else:
            exit("Could not determine left table for join")

    # left_table_name is the alias/table name as it appears in the query
    # variables["row_identity"] is keyed by alias_map.keys() which are aliases/table names

    encoding = True

    global left_join_func, right_join_func, full_join_func
    left_join_func = Function("left_join_func", IntSort(), IntSort(), BoolSort())
    right_join_func = Function("right_join_func", IntSort(), IntSort(), BoolSort())
    full_join_func = Function('full_join_func', IntSort(), IntSort(), BoolSort())

    for i in range(len(joins)) :
        join = joins[i]
        cond = join.args.get("on")
        encoded_cond = encode_condition(cond, idx, variables)

        # Extract right table from join - handle Table expression
        right_table_expr = join.args.get("this")
        if isinstance(right_table_expr, exp.Table):
            right_table_name = right_table_expr.name
        else:
            exit(f"Unexpected join table structure: {right_table_expr}")

        # right_table_name is the alias/table name as it appears in the query
        # Resolve to real table names for consistency (but use alias for accessing variables)
        left_table_real = alias_map.get(left_table_name, left_table_name)
        right_table_real = alias_map.get(right_table_name, right_table_name)

        # Check if WHERE clause filters on the "other side" of an outer join
        # This effectively converts the outer join to an inner join
        should_be_inner = False
        if join.side:
            side = join.side.lower()
            if side == "left" and right_table_real in where_tables:
                # LEFT JOIN with WHERE filtering on right table -> INNER JOIN
                should_be_inner = True
            elif side == "right" and left_table_real in where_tables:
                # RIGHT JOIN with WHERE filtering on left table -> INNER JOIN
                should_be_inner = True
            elif side == "full" and (left_table_real in where_tables or right_table_real in where_tables):
                # FULL JOIN with WHERE filtering on either side -> INNER JOIN
                should_be_inner = True

        # print(f"line228, left_table = {left_table_name}, right_table = {right_table_name}")
        if (not join.side) or should_be_inner: # inner join (explicit or converted from outer)
            # for inner loop, it doesn't matter if the condition is placed in ON or WHERE clause
            # since we always use AND to connect them.
            temp = encoded_cond
        else: # outer join
            side = join.side.lower()
            # Use real table names for row_identity (both alias and real name point to same variable)
            left_row = variables["row_identity"][left_table_real]
            right_row = variables["row_identity"][right_table_real]

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
def encode_where_clause(ast, idx, variables):
    where = ast.args.get("where")
    if not where:
        return BoolVal(True)

    expr = where.this
    return encode_condition(expr, idx, variables)


def encode_condition(expr, idx, variables):
    key = expr.key.lower()

    # for now, we're only handling simple comparisons: <, >, =, <=, >=
    # and, or, not, is (IS NULL / IS NOT NULL)
    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(idx, left, right, key, variables)
            if constraint is not None:
                # print(f"Added constraint: {constraint}") #for debug use
                return constraint
        elif key == "and":
            return And(encode_condition(expr.args["this"], idx, variables),
                   encode_condition(expr.args["expression"], idx, variables))
        elif key == "or":
            return Or(encode_condition(expr.args["this"], idx, variables),
                   encode_condition(expr.args["expression"], idx, variables))
        elif key == "not":
            return Not(encode_condition(expr.args["this"], idx, variables))
        elif key == "is":
            return encode_is_null(expr, idx, variables)

    exit(f"Unsupported type: {key}")



# encode IS NULL and IS NOT NULL conditions
def encode_is_null(expr, idx, variables):
    global NULL
    # expr is an exp.Is condition
    # expr.args["this"] is the column/expression being checked
    # expr.args["expression"] should be exp.Null() for IS NULL
    # Check if negated (IS NOT NULL) via the negated attribute

    column_expr = expr.args.get("this")
    null_expr = expr.args.get("expression")

    # Encode the column/expression
    var, var_type = encode_expr(idx, column_expr, variables)

    # Check if this is IS NULL or IS NOT NULL
    # sqlglot uses exp.Null for NULL, and may have a negated flag
    is_negated = getattr(expr, 'negated', False)

    # If expression is exp.Null, it's a NULL check
    if isinstance(null_expr, exp.Null):
        if is_negated:
            # IS NOT NULL: column != NULL
            return var != NULL
        else:
            # IS NULL: column == NULL
            return var == NULL
    else:
        # IS something else (not just NULL check) - treat as equality
        null_val, _ = encode_expr(idx, null_expr, variables)
        if is_negated:
            return var != null_val
        else:
            return var == null_val


# convert a simple comparison expression to a Z3 constraint
def encode_comparison(idx, left, right, op, variables):
    # print(f"line306, left = {left}, right = {right}")
    var, _ = encode_expr(idx, left, variables)
    right_val, _ = encode_expr(idx, right, variables)

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


def encode_expr(idx, expr, variables):
    global q1_alias_map, q2_alias_map
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map
    # literals
    if isinstance(expr, exp.Literal):
        if expr.is_int:
            return IntVal(str(expr)), "INT"
        if expr.is_number:
            return RealVal(str(expr)), "REAL" #must use RealVal instead of Real
        if expr.is_string:
            return StringVal(expr.this), "STRING"
        else:
            exit(f"unknown type for {expr}")

    if isinstance(expr, exp.Condition):
        key = expr.key.lower()
        # handle math ops
        if key in ["add", "sub", "mul"]:
            left, right = expr.args["this"], expr.args["expression"]
            left, left_type = encode_expr(idx, left, variables)
            right, right_type = encode_expr(idx, right, variables)

            if (left_type == "STRING" or right_type == "STRING"):
                exit("cannot perform arithematic operation on String type")
            elif ((left_type != "INT" and left_type != "REAL") and
                  (right_type != "INT" and right_type != "REAL") and (left_type != right_type)):
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
        table = alias_map[str(expr.table)]
        column = str(expr.this)

        # if table in variables.keys():
        #     if column in variables[table]:
        #         return variables[table][column], schema[table][column]
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

    # todo: need to edit the following block of code a bit for Z3.Function
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