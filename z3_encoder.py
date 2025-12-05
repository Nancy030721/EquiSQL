import sys
from sqlglot import expressions as exp
from z3 import *


def encode(sch, q1_ast, q2_ast, map1, map2, nn, pk):
    # step 0: read inputs, define and initialize global variables
    global s, q1_alias_map, q2_alias_map, q1_constraints, q2_constraints, vars, JOIN, schema, not_nulls
    
    s = Solver()
    JOIN = Function('JOIN', IntSort(), IntSort(), BoolSort())
    q1_alias_map, q2_alias_map, schema, not_nulls = map1, map2, sch, nn
    q1_constraints, q2_constraints = [], []
    
    # step 1: declare variables
    vars = declare_variables(schema)

    # step 2: enforce that input tuples are the same 
    # SKIPPED, now we are directly using the same set of variables 
    
    # step 3: encode constraints for each query
    encode_query(q1_ast, idx=1)
    encode_query(q2_ast, idx=2)
    s.add(q1_constraints)
    s.add(q2_constraints)

    # step 4:
    s.add(encode_diff())
   
    return s


def encode_diff() :
    global q1_where_vars, q2_where_vars
    return Or(
        q1_where_vars["after_match"] != q2_where_vars["after_match"],
        q1_where_vars["after_rnull"]  != q2_where_vars["after_rnull"],
        q1_where_vars["after_lnull"]  != q2_where_vars["after_lnull"],
    )


# declare Z3 variables for all attributes in all tables
# returns a map, which maps dict[table][column] -> Z3 variable
def declare_variables(schema):  
    global not_nulls
    variables = {}
    variables["present"] = {}

    for table in schema.keys():        
        variables["present"][table] = Bool(f"{table}_present")

    for table in schema.keys():
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{column}"
            if col_type == "INT":
                variables[table][column] = Int(var_name)
            elif col_type =="STRING":
                variables[table][column] = String(var_name)
            else: #col_type == "REAL"
                variables[table][column] = Real(var_name)
            # add 'is_null' flags for every attribute
            if table in not_nulls and column in not_nulls[table]:
                variables[table][f"{column}_is_null"] = BoolVal(False)
            else: 
                variables[table][f"{column}_is_null"] = Bool(f"{table}_{column}_is_null") 
    
    return variables



def encode_query(ast, idx):
    join_type = encode_join(ast, idx)
    encode_where(ast, idx, join_type)


def encode_where(ast, idx, join_type):
    if idx == 1:
        global q1_constraints, q1_join_vars
        constraints, join_vars = q1_constraints, q1_join_vars
    else:
        global q2_constraints, q2_join_vars
        constraints, join_vars = q2_constraints, q2_join_vars

    # create after-where booleans
    q_after_match      = Bool(f"q{idx}_after_match")
    q_after_right_null = Bool(f"q{idx}_after_right_null")
    q_after_left_null  = Bool(f"q{idx}_after_left_null")

    where = ast.args.get("where")
    if where:
        cond_where = encode_condition(where.this, idx, where=True)
    else: 
        cond_where = BoolVal(True)
    
    # no join --> single row only
    if join_type == "no_join":
        constraints += [
            q_after_match      == cond_where,
            q_after_right_null == False,   # null rows filtered
            q_after_left_null  == False,
        ]
    else :
        # print(f"line99, idx={idx}")
        # get the actual join variables created earlier
        q_match      = join_vars["match"]
        q_right_null = join_vars["rnull"]
        q_left_null  = join_vars["lnull"]

        constraints += [
            q_after_match      == And(q_match, cond_where),
            q_after_right_null == And(q_right_null, cond_where),
            q_after_left_null  == And(q_left_null, cond_where),
        ]

    # store them for projection or final comparison
    if idx == 1:
        global q1_where_vars
        q1_where_vars = {
            "after_match":      q_after_match,
            "after_rnull":      q_after_right_null,
            "after_lnull":      q_after_left_null
        }
    else:
        global q2_where_vars
        q2_where_vars = {
            "after_match":      q_after_match,
            "after_rnull":      q_after_right_null,
            "after_lnull":      q_after_left_null
        }



# DONE
def encode_condition(expr, idx, where=False):
    key = expr.key.lower()

    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq", "neq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(idx, left, right, key, where)
            if constraint is not None:
                return constraint
        elif key == "and":
            # not perfect SQL semantics (stricter than SQL), but still works
            return And(encode_condition(expr.args["this"], idx, where),
                   encode_condition(expr.args["expression"], idx, where))
        elif key == "or":
            return Or(encode_condition(expr.args["this"], idx, where),
                   encode_condition(expr.args["expression"], idx, where))
        elif key == "not": # (T.sid IS NOT NULL) is parsed as (NOT T.sid IS NULL)
            return Not(encode_condition(expr.args["this"], idx, where))
        elif key == "is":
            _, _, col_is_null = encode_expr(idx, expr.this, where)              
            return col_is_null[0]
        # elif key == "like":
        #     print(expr.this)
        #     print(expr.expression)
        #     print("tidi")
    exit(f"Unsupported type: {key}")


# def encode_pattern(idx, col, pattern, where=False) {
#     # tidi
#     col, _, col_is_null= encode_expr(idx, col, where)
#     return And(Not(col_is_null), LIKE(col, pattern))
# }

def encode_comparison(idx, left, right, op, where):
    left, _, lcols = encode_expr(idx, left, where)
    right, _, rcols = encode_expr(idx, right, where)

    left_null  = Or(BoolVal(False), *lcols)   # left is null, if any columns in it is null. e.g. A + B = C+3, left_null = OR(A_is_null, B_is_null)
    right_null = Or(BoolVal(False), *rcols)

    return sql_cmp_base(left, left_null, right, right_null, op)


def sql_cmp_base(left_val, left_null, right_val, right_null, op):
    both_not_null = And(Not(left_null), Not(right_null))
    if op == "eq":     # =
        return And(both_not_null, left_val == right_val)
    elif op == "neq":  # <> 
        return And(both_not_null, left_val != right_val)
    elif op == "gt":   # >
        return And(both_not_null, left_val > right_val)
    elif op == "lt":   # <
        return And(both_not_null, left_val < right_val)
    elif op == "gte":  # >=
        return And(both_not_null, left_val >= right_val)
    elif op == "lte":  # <=
        return And(both_not_null, left_val <= right_val)
    else:
        raise ValueError(f"Unknown comparison op: {op}")



    
# DONE 
def encode_expr(idx, expr, where=False):
    # literals
    if isinstance(expr, exp.Literal):
        if expr.is_int:
            return IntVal(str(expr)), "INT", []
        if expr.is_number:
            return RealVal(str(expr)), "REAL", []
        if expr.is_string:
            return StringVal(expr.this), "STRING", []
        else:
            exit(f"unknown type for {expr}")

    if isinstance(expr, exp.Condition):
        key = expr.key.lower()
        if key in ["add", "sub", "mul"]:
            left, right = expr.args["this"], expr.args["expression"]
            left, ltype, lcols = encode_expr(idx, left, where)
            right, rtype, rcols = encode_expr(idx, right, where)
            
            if (ltype == "STRING" or rtype == "STRING"):
                exit("cannot perform arithematic operation on String type")
            if not (ltype in ["INT", "REAL"] and rtype in ["INT", "REAL"]):
                exit(f"type mismatch between {ltype} and {rtype}")

            if key == "add":
                return left + right, ltype, lcols + rcols
            elif key == "sub":
                return left - right, ltype, lcols + rcols
            elif key == "mul":
                return left * right, ltype, lcols + rcols
            else:
                raise ValueError(f"Unsupported math operation {key}")
   

    if isinstance(expr, exp.Column):
        global q1_alias_map, q2_alias_map, vars, schema
        if (idx == 1): 
            alias_map = q1_alias_map
        elif (idx == 2):
            alias_map = q2_alias_map

        table = alias_map[str(expr.table)]
        column = str(expr.this)
        if not where:
            return vars[table][column], schema[table][column], [vars[table][f"{column}_is_null"]]
        else:
            return vars[f"J{idx}_{table}_{column}"], schema[table][column], [vars[f"J{idx}_{table}_{column}_is_null"]]
    
    raise Exception(f"encode_expr: could not resolve {expr} in query{idx}")



# return left_table, right_table, join_type 
def get_join_tables_and_type(ast, joins) :
    # when there's no join at all 
    if (not joins or len(joins) == 0) :
        return ast.args.get("from").this, None, "no_join"  
    
    join = joins[0] 
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

    if left_table_name is None:
        exit("Could not determine left table for join")
    
    right_table_expr = join.args.get("this")
    right_table_name = right_table_expr.name

    # cartisian product 
    if not join.args.get("on"): 
        return left_table_name, right_table_name, "CP"

    # inner join
    if not join.side:
        return left_table_name, right_table_name, "INNER"  

    # outer join 
    return left_table_name, right_table_name, join.side.upper()



def allocate_join_result_vars(idx):
    global vars

    for table, columns in schema.items():
        for col, type in columns.items():
            # value variable for query idx
            var_name = f"J{idx}_{table}_{col}"
            if type == "INT":
                val = Int(var_name)
            elif type == "REAL":
                val = Real(var_name)
            else:
                val = String(var_name)

            # null flag variable for query idx
            null_name = f"J{idx}_{table}_{col}_is_null"
            is_null = Bool(null_name)

            vars[f"J{idx}_{table}_{col}"] =  val
            vars[f"J{idx}_{table}_{col}_is_null"] = is_null



def encode_join(ast, idx):
    # pick which query (q1 or q2)
    if idx == 1:
        global q1_alias_map, q1_constraints, vars
        alias_map  = q1_alias_map
        constraints = q1_constraints
        allocate_join_result_vars(idx=1)
    else:
        global q2_alias_map, q2_constraints, vars
        alias_map  = q2_alias_map
        constraints = q2_constraints
        allocate_join_result_vars(idx=2)

    # produce NEW join booleans for this query
    q_match      = Bool(f"q{idx}_match")
    q_right_null = Bool(f"q{idx}_right_null")
    q_left_null  = Bool(f"q{idx}_left_null")
    if idx == 1: 
        global q1_join_vars
        q1_join_vars = {
            "match":      q_match,
            "rnull":      q_right_null,
            "lnull":      q_left_null
        }
    else: 
        global q2_join_vars
        q2_join_vars = {
            "match":      q_match,
            "rnull":      q_right_null,
            "lnull":      q_left_null
        }

    joins = ast.args.get("joins") 
    # identify tables + join type
    left_table_name, right_table_name, jtype = get_join_tables_and_type(ast, joins)

    if jtype == "no_join":
        constraints += encode_join_result(idx, left_table_name, right_table_name, jtype) # right_table_name = None 
    else: 
        # resolve real table names (consider alias)
        left_real  = alias_map.get(left_table_name, left_table_name)
        right_real = alias_map.get(right_table_name, right_table_name)

        left_present  = vars["present"][left_real]
        right_present = vars["present"][right_real]

        # handle cartesian product
        if jtype == "CP":
            constraints += encode_cartisian_product(left_present, right_present,
                                                    q_match, q_right_null, q_left_null)
        else: 
            # compute ON predicate
            join = joins[0]
            cond = join.args.get("on")
            on_pred = encode_condition(cond, idx)
            # print(f"line374, on_pred = {on_pred}")

            # join type handlers
            if jtype == "INNER":
                constraints += encode_inner_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null)
            elif jtype == "LEFT":
                constraints += encode_left_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null, right_table_name)
            elif jtype == "RIGHT":
                # constraints += encode_right_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null, left_table_name)
                constraints += encode_left_join(on_pred, right_present, left_present, q_match, q_right_null, q_left_null, left_table_name)
            elif jtype == "FULL":
                constraints += encode_full_join(on_pred, left_present, right_present, q_match, q_left_null, q_right_null, left_table_name, right_table_name)
            else:
                raise ValueError(f"Unknown join type {jtype}")
        
        constraints += encode_join_result(idx, left_real, right_real, jtype)

    return jtype



def encode_cartisian_product(left_present, right_present, q_match, q_right_null, q_left_null):
    return [
        q_match      == And(left_present, right_present),
        q_right_null == False,
        q_left_null  == False,
    ]


def encode_inner_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null):
    return [
        q_match      == And(And(left_present, right_present), on_pred),
        q_right_null == False,
        q_left_null  == False,
    ]
    


def encode_left_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null, right_table):
    return [
        q_match == And(And(left_present, right_present), on_pred),
        q_right_null == And(left_present, Not(on_pred)),
        q_left_null == False 
    ]


def encode_full_join(on_pred, left_present, right_present, q_match, q_left_null, q_right_null, left_table, right_table):
    return [
        q_match == And(And(left_present, right_present), on_pred),
        q_right_null == And(left_present, Not(on_pred)),
        q_left_null == And(right_present, Not(on_pred)), 
    ]



def encode_join_result(idx, left_table, right_table, join_type):
    global vars, schema, q1_join_vars, q2_join_vars
    if (idx == 1): 
        match, left_null, right_null = q1_join_vars["match"], q1_join_vars["lnull"], q1_join_vars["rnull"]
    else: 
        match, left_null, right_null = q2_join_vars["match"], q2_join_vars["lnull"], q2_join_vars["rnull"]
    
    constraints = []
    def null_literal(type):
        if type == "INT": return IntVal(0)
        if type == "REAL": return RealVal(0)
        return StringVal("")

    for table, columns in schema.items():
        if join_type == "no_join": 
            use_base = BoolVal(True)
        elif join_type == "INNER" or join_type == "CP":
            use_base = match

        elif join_type == "LEFT":
            if table == left_table:
                use_base = Or(match, right_null)
            else:
                use_base = match

        elif join_type == "RIGHT":
            if table == right_table:
                use_base = Or(match, left_null)
            else:
                use_base = match

        elif join_type == "FULL":
            if table == left_table:
                use_base = Or(match, right_null)
            else:
                use_base = Or(match, left_null)

        for col, ctype in columns.items():
            # for each attribute in the original table, read its variable and if it is (not) null
            base_val   = vars[table][col]
            base_is_null = vars[table][f"{col}_is_null"]

            J_val  = vars[f"J{idx}_{table}_{col}"]
            J_null = vars[f"J{idx}_{table}_{col}_is_null"]

            null_val = null_literal(ctype)
            
            constraints.append(J_val  == If(use_base, base_val,  null_val))
            constraints.append(J_null == If(use_base, base_is_null, True))

    return constraints



def encode_cols_null(table):
    global schema, vars 
    cols_is_null = BoolVal(True)
    for column, _ in schema[table].items():
        cols_is_null = And(cols_is_null, vars[table][f"{column}_is_null"])
    return cols_is_null
    

    
def exit(err_message):
    print(err_message)
    sys.exit(1)