import sys
from sqlglot import expressions as exp
from z3 import *


def encode(schema, q1_ast, q2_ast, alias_map_1, alias_map_2, nf):
    # define and initialize global variables
    global s, NULL, q1_alias_map, q2_alias_map, null_funcs, vars
    s = Solver()
    NULL = IntVal(-1)
    q1_alias_map = alias_map_1
    q2_alias_map = alias_map_2
    null_funcs = nf
    
    
    # step 1: declare variables for each query 
    vars_q1 = declare_variables(schema, idx="q1")
    vars_q2 = declare_variables(schema, idx="q2")
    vars = declare_variables(schema, idx="")

    print(vars)


    # step 2: enforce that input tuples are the same 
    for table in schema:
        if table in q1_alias_map.values() and table in q2_alias_map.values():
            for col in schema[table]:
                s.add(vars_q1[table][col] == vars_q2[table][col])
 
    # step 3: add constraints 
    cond_q1 = encode_query(schema, q1_ast, 1, vars_q1)
    cond_q2 = encode_query(schema, q2_ast, 2, vars_q2)

    # print("encoding for query1:", cond_q1) # for debug use
    # print("encoding for query2:", cond_q2) # for debug use

    # step 4: ask -- is it possible that some variable makes q1 XOR q2
    q1_result = Bool("q1_result")
    q2_result = Bool("q2_result")
    s.add(q1_result == cond_q1)
    s.add(q2_result == cond_q2)
    s.add(q1_result != q2_result)
   
    return s


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

    # synthetic row identity
    for table in alias_map.values():        
        variables["row_identity"][table] = Int(f"{table}_row")

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
    
    return variables



def encode_query(schema, ast, idx, variables):
    # Check if WHERE clause filters on the "other side" of outer joins
    # This effectively converts outer joins to inner joins
    where = ast.args.get("where")
    if where:
        # Extract tables referenced in WHERE clause
        where_tables = extract_tables_from_condition(where.this, idx)
        # Modify join encoding if WHERE filters on other side
        cond_join = encode_join(schema, ast, idx, variables, where_tables)
    else:
        cond_join = encode_join(schema, ast, idx, variables, set())
    cond_where = encode_where(schema, ast, idx, variables)
    return And(cond_join, cond_where)

# Extract tables referenced in a condition expression
def extract_tables_from_condition(expr, idx):
    # if side == "left" and right_table_real in where_tables:
    #             # LEFT JOIN with WHERE filtering on right table -> INNER JOIN
    #             should_be_inner = True
    #         elif side == "right" and left_table_real in where_tables:
    #             # RIGHT JOIN with WHERE filtering on left table -> INNER JOIN
    #             should_be_inner = True
    #         elif side == "full" and (left_table_real in where_tables or right_table_real in where_tables):
    #             # FULL JOIN with WHERE filtering on either side -> INNER JOIN
    #             should_be_inner = True

    # it looks like we skip conditions in where when
    # A left join B, and B exists in where
    # A right join B, and A exists in where
    # A full join B, and either A or B exists in where

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


def encode_join(schema, ast, idx, variables, where_tables=None):
    print(f"line124, query {idx}, where_table = {where_tables}")
    global q1_alias_map, q2_alias_map
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map

    if where_tables is None:
        where_tables = set()
    
    encoding = BoolVal(True) 
    joins = ast.args.get("joins")
    # no (explicit) joins
    if not joins or (len(joins) == 1 and (joins[0].args.get("on")) is None):
        return encoding

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


    for i in range(len(joins)) :
        join = joins[i]
        cond = join.args.get("on")
        encoded_cond = encode_condition(schema, cond, idx, variables, join=True)

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

        left_row = variables["row_identity"][left_table_real]
        right_row = variables["row_identity"][right_table_real]
        
        if (not join.side) or should_be_inner: # inner join (explicit or converted from outer)
            # for inner loop, it doesn't matter if the condition is placed in ON or WHERE clause
            # since we always use AND to connect them.

            # todo: add constarint that left and right are not null
            print(f"line209, performing inner join on query {idx}")
            global vars
            left, left_type = encode_expr(schema, idx, cond.args["this"], vars)
            right, right_type = encode_expr(schema, idx, cond.args["expression"], vars)

            print(left, left_type, right, right_type)
            temp = And(And(encoded_cond, (Not (encode_is_null(left, left_type)))), (Not (encode_is_null(right, right_type))))
        
        else: # outer join
            LeftJoin = Function("LeftJoin", IntSort(), IntSort(), BoolSort())
            FullJoin = Function('FullJoin', IntSort(), IntSort(), BoolSort())

            if (side == "left") :
                temp = encode_left_join(encoded_cond, left_row, right_row, LeftJoin, schema)
            elif (side == "right") :
                temp = encode_left_join(encoded_cond, right_row, left_row, LeftJoin, schema)
            elif (side == "full") :
                temp = encode_full_join(encoded_cond, left_row, right_row, FullJoin)
            else:
                exit(f"unknown join type: {side.upper()} JOIN")

        encoding = And(temp, encoding)

    return encoding

# todo
def encode_left_join(on_pred, left_row, right_row, LeftJoin, schema):
    global NULL
    return And(
        (Not (encode_is_null(left_row, "INT"))), #left key is not null
        Implies(on_pred, LeftJoin(left_row, right_row)),
        Implies(Not(on_pred), LeftJoin(left_row, NULL)),
        Implies(LeftJoin(left_row, right_row), on_pred)
    )

def encode_full_join(on_pred, left_row, right_row, FullJoin):
    global NULL
    # s.add(FullJoin(left_row, right_row) == FullJoin(right_row, left_row))
    return And(
        Implies(on_pred, FullJoin(left_row, right_row)),
        Implies(Not(on_pred), And(FullJoin(NULL, right_row), FullJoin(left_row, NULL))),
        Implies(FullJoin(left_row, right_row), on_pred) 
    )
    

# add constraints for simple WHERE clauses like 'R.age > 20' or 'T.id = 3'.
def encode_where(schema, ast, idx, variables):
    where = ast.args.get("where")
    if not where:
        return BoolVal(True)

    expr = where.this
    encoding = encode_condition(schema, expr, idx, variables)
    print(f"line261, encoding for where clause for query {idx} is {encoding}")
    return encoding



def encode_condition(schema, expr, idx, variables, join=False):
    global vars
    key = expr.key.lower()

    # for now, we're only handling simple comparisons: <, >, =, <=, >=
    # and, or, not, (IS NULL / IS NOT NULL)
    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(schema, idx, left, right, key, variables)
            if constraint is not None:
                if (not join) :
                    # add constraint saying that both sides cannot be null
                    # tidi
                    left, left_type = encode_expr(schema, idx, left, vars)
                    right, right_type = encode_expr(schema, idx, right, vars)
                    # print(left, left_type, right, right_type)
                    return And(And(constraint, (Not (encode_is_null(left, left_type)))), (Not (encode_is_null(right, right_type))))
                
                return constraint
        elif key == "and":
            return And(encode_condition(schema, expr.args["this"], idx, variables),
                   encode_condition(schema, expr.args["expression"], idx, variables))
        elif key == "or":
            return Or(encode_condition(schema, expr.args["this"], idx, variables),
                   encode_condition(schema, expr.args["expression"], idx, variables))
        elif key == "not":
            return Not(encode_condition(schema, expr.args["this"], idx, variables))
        elif key == "is":
            # todo
            print(f"line294, {expr}")
            name, type = encode_expr(schema, idx, expr.this, vars)
            return encode_is_null(name, type)

    exit(f"Unsupported type: {key}")



# convert a simple comparison expression to a Z3 constraint
def encode_comparison(schema, idx, left, right, op, variables):
    # print(f"line306, left = {left}, right = {right}")
    var, _ = encode_expr(schema, idx, left, variables)
    right_val, _ = encode_expr(schema, idx, right, variables)

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

# encode IS NULL and IS NOT NULL conditions
# todo
def encode_is_null(col_name, col_type="INT"):
    global null_funcs, vars
        
    if col_type == "INT":
        return null_funcs[0](col_name)
    elif col_type =="STRING":
        return null_funcs[1](col_name)
    else: #col_type == "REAL"
        return null_funcs[2](col_name)

        

def encode_expr(schema, idx, expr, variables):
    global q1_alias_map, q2_alias_map
    if (idx == 1): 
        alias_map = q1_alias_map
    elif (idx == 2):
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
            left, left_type = encode_expr(schema, idx, left, variables)
            right, right_type = encode_expr(schema, idx, right, variables)
            
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
        return variables[table][column], schema[table][column]
    
    exit(f"encode_expr: could not resolve {expr}")


def exit(err_message):
    print(err_message)
    sys.exit(1)