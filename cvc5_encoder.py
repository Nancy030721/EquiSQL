import sys
from sqlglot import expressions as exp
import cvc5
from cvc5 import Kind


def encode(schema, q1_ast, q2_ast, map1, map2, nn, pk):
    # step 0: read inputs, define and initialize global variables
    global s, NULL, q1_alias_map, q2_alias_map, has_joins, q2_has_join, not_null, primary_keys, vars, null_funcs, variables_to_interpret
    # global distinct_funcs

    s = cvc5.Solver()
    s.setLogic("ALL") 
    s.setOption("produce-models", "true")
    s.setOption("produce-unsat-cores", "true")

    # this causes error because the second argument is name for variable, that has type str
    # NULL = s.mkConst(s.getIntegerSort(), -1) 
    NULL = s.mkConst(s.getIntegerSort(), "NULL")
    # eq_null = s.mkTerm(Kind.EQUAL, NULL, s.mkInteger(-1))
    # s.assertFormula(eq_null)
    variables_to_interpret = set()

    
    q1_alias_map, q2_alias_map, not_null, primary_keys = map1, map2, nn, pk
    null_funcs = []
    null_funcs.append(s.mkConst(s.mkFunctionSort([s.getIntegerSort()], s.getBooleanSort()), "NullInt"))
    null_funcs.append(s.mkConst(s.mkFunctionSort([s.getStringSort()], s.getBooleanSort()), "NullString"))
    null_funcs.append(s.mkConst(s.mkFunctionSort([s.getRealSort()], s.getBooleanSort()), "NullReal"))
    # distinct_funcs = []
    # distinct_funcs.append(s.mkConst(s.mkFunctionSort([s.getIntegerSort()], s.getBooleanSort()), "DistinctInt"))
    # distinct_funcs.append(s.mkConst(s.mkFunctionSort([s.getStringSort()], s.getBooleanSort()), "DistinctString"))
    # distinct_funcs.append(s.mkConst(s.mkFunctionSort([s.getRealSort()], s.getBooleanSort()), "DistinctReal"))

    has_joins = [False, False]
    
    # step 1: declare variables for each query 
    vars_q1 = declare_variables(schema, idx="q1")
    vars_q2 = declare_variables(schema, idx="q2")
    vars = declare_variables(schema, idx="") # created these for IS (NOT) NULL


    # step 2: enforce that input tuples are the same 
    for table in schema:
        if table in q1_alias_map.values() and table in q2_alias_map.values():
            for col in schema[table]:
                s.assertFormula(s.mkTerm(Kind.EQUAL, vars_q1[table][col], vars_q2[table][col]))
 
    # new added
    global q1_used_terms, q2_used_terms   
    q1_used_terms, q2_used_terms = set(), set()

    # step 3: encode constraints for each query
    cond_q1 = encode_query(schema, q1_ast, 1, vars_q1)
    cond_q2 = encode_query(schema, q2_ast, 2, vars_q2)

    # print("encoding for query1:", cond_q1) # for debug use
    # print("encoding for query2:", cond_q2) # for debug use

    # step 4: ask -- is it possible that some variable makes q1 XOR q2
    q1_result = s.mkConst(s.getBooleanSort(), "q1_result")
    q2_result = s.mkConst(s.getBooleanSort(), "q2_result")
    s.assertFormula(s.mkTerm(Kind.EQUAL, q1_result, cond_q1))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q2_result, cond_q2))
    s.assertFormula(s.mkTerm(Kind.NOT, s.mkTerm(Kind.EQUAL, q1_result, q2_result)))

    variables_to_interpret.add(q1_result)
    variables_to_interpret.add(q2_result)

    return s, variables_to_interpret 


# for each table in both queries, declare Z3 variables for its columns
# returns a map, which maps dict[table][column] -> Z3 variable
def declare_variables(schema, idx):
    global s, q1_alias_map, q2_alias_map
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map
        
    variables = {}
    variables["row_identity"] = {}

    # synthetic row identity
    for table in alias_map.values():        
        variables["row_identity"][table] = s.mkConst(s.getIntegerSort(), f"{table}_row")

    for table in alias_map.values():
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{idx}_{column}"
            if col_type == "INT":
                variables[table][column] = s.mkConst(s.getIntegerSort(), var_name)
            elif col_type =="STRING":
                variables[table][column] = s.mkConst(s.getStringSort(), var_name)
            else: #col_type == "REAL"
                variables[table][column] = s.mkConst(s.getRealSort(), var_name)
    
    if idx != "":
        extract_values(variables.values())
    # extract_values(variables.values())
    return variables


def extract_values(nested):
    global variables_to_interpret
    for block in nested:
        for k, term in block.items():
            variables_to_interpret.add(term)


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

    cond_primary_keys = encode_not_null_for_primary_keys(schema, idx)
    
    return s.mkTerm(Kind.AND, cond_join, cond_where, cond_primary_keys)

# Extract tables referenced in a condition expression
def extract_tables_from_condition(expr, idx):
    # it looks like we skip conditions in where
    # A left join B, and B exists in where
    # A right join B, and A exists in where
    # A full join B, and either A or B exists in where

    # 1.if you see "A.id IS NULL", will that be treated as inner join? -- no
    # 2.if you see "A.id IS NOT NULL", will that be treated as inner join? -- actually, not really 
    #   e.g. 
    #        SELECT FROM R FULL JOIN S ON R.id=S.id WHERE R.id IS NOT NULL -- yes, treat as inner join 
    #        SELECT FROM R FULL JOIN S ON R.id=S.id WHERE S.id IS NOT NULL -- yes, treat as inner join 
    #        SELECT FROM R FULL JOIN S ON R.id=S.id WHERE S.id IS NOT NULL AND S.id IS NOT NULL -- yes, treat as inner join 
    #        SELECT FROM R FULL JOIN S ON R.id=S.id WHERE R.id IS NOT NULL OR S.id IS NOT NULL -- NO!  
    
    # can we always choose only one side (either left or right) of OR? 
    #   e.g.
    #        SELECT FROM R LEFT JOIN S ON R.id=S.id WHERE R.id IS NOT NULL OR S.id > 15
    #           --- used to have wheretables = {R, S}, so will be treated as inner join as S in wheretables
    #           --- if use wheretables = {R}, this will not be treated as inner join 
    #        SELECT FROM R FULL JOIN S ON R.id=S.id WHERE R.id IS NOT NULL OR S.id IS NULL OR S.id > 15
    #           --- used to have wheretables = {R, S} 
    #           --- if use wheretables = {R}, this will not be treated as inner join -- no effects 
    

    global s, q1_alias_map, q2_alias_map
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
        # new implementation:
        elif key in ["and"]:
            tables.update(extract_tables_from_condition(expr.args["this"], idx))
            tables.update(extract_tables_from_condition(expr.args["expression"], idx))
        elif key in ["or"]:
            left_tables = extract_tables_from_condition(expr.args["this"], idx)
            right_tables = extract_tables_from_condition(expr.args["expression"], idx)
            for table in left_tables : 
                if (table in right_tables): 
                    tables.add(table)
        elif key == "not":
            tables.update(extract_tables_from_condition(expr.args["this"], idx))

    return tables

# return true if explicit join(s) is found in ast, false otherwise 
def explicit_join_found(ast):
    joins = ast.args.get("joins")
    return not (not joins or (len(joins) == 1 and (joins[0].args.get("on")) is None))
    

def encode_join(schema, ast, idx, variables, where_tables=None):
    global s, q1_alias_map, q2_alias_map, has_joins
    if (idx == 1):
        alias_map = q1_alias_map
    else:
        alias_map = q2_alias_map

    if where_tables is None:
        where_tables = set()
    
    encoding = s.mkTrue()
    if not explicit_join_found(ast):
        return encoding
    has_joins[idx-1] = True

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

    joins = ast.args.get("joins")
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

            # for inner join, add constarint that left and right are not null            
            # doesn't work rn, example:
                    # SELECT Students.name
                    # FROM Students
                    # JOIN Takes ON Takes.sid = Students.id
                    # OR Students.id >= 3
            # at this time, neither left or right is an expression, so we cannot get the type and set those to be not null
            # I think we can implement a helper method, which go through every expr and decide whether we add a (NOT NULL) constraint on it
            try: 
                temp = encode_nulls(schema, cond, idx, encoded_cond)
                # print(f"line274, query{idx}, temp={temp}")
            except Exception as e:
                exit(f"line277, Error: {e}")

            
        else: # outer join
            join_sort = s.mkFunctionSort([s.getIntegerSort(), s.getIntegerSort()], s.getBooleanSort())
            Join = s.mkConst(join_sort, "Join")

            if (side == "left") :
                temp = encode_left_join(encoded_cond, left_row, right_row, Join)
            elif (side == "right") :
                temp = encode_left_join(encoded_cond, right_row, left_row, Join)
            elif (side == "full") :
                temp = encode_full_join(encoded_cond, left_row, right_row, Join)
            else:
                exit(f"unknown join type: {side.upper()} JOIN")

        encoding = s.mkTerm(Kind.AND, temp, encoding)

    return encoding

                    
def encode_nulls(schema, expr, idx, temp):
    global s, vars
    # print(f"line305, encode_nulls({expr}) in query{idx}")
    key = expr.key.lower()

    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq"]:
            left, right = expr.args["this"], expr.args["expression"]
            lnames, ltypes = encode_nulls_helper(schema, idx, left, vars)
            rnames, rtypes = encode_nulls_helper(schema, idx, right, vars)
            lnotnull, rnotnull = s.mkTrue(), s.mkTrue()
            for i in range(len(lnames)):
                lnotnull = s.mkTerm(Kind.AND, lnotnull, s.mkTerm(Kind.NOT, encode_is_null(lnames[i], ltypes[i])))
            for i in range(len(rnames)):
                rnotnull = s.mkTerm(Kind.AND, rnotnull, s.mkTerm(Kind.NOT, encode_is_null(rnames[i], rtypes[i])))
            if len(lnames) > 0:
                temp = s.mkTerm(Kind.AND, temp, lnotnull)
            if len(rnames) > 0:
                temp = s.mkTerm(Kind.AND, temp, rnotnull)
            # temp = s.mkTerm(Kind.AND, temp, s.mkTerm(Kind.AND, lnotnull, rnotnull))

        elif key in ["and", "or"]:
            left =  encode_nulls(schema, expr.args["this"], idx, s.mkTrue())
            right = encode_nulls(schema, expr.args["expression"], idx, s.mkTrue())
            if key == "and": 
                temp = s.mkTerm(Kind.AND, temp, s.mkTerm(Kind.AND, left, right))
            else :
                temp = s.mkTerm(Kind.AND, temp, s.mkTerm(Kind.OR, left, right))
                    
        elif key == "not":
            temp = encode_nulls(schema, expr.args["this"], idx, temp)

        elif key == "is":
            names, types = encode_nulls_helper(schema, idx, expr.this, vars)
            # print(f"line325, name={Z3_get_probe_name_bytes}")
            for i in range(len(names)):
                temp = s.mkTerm(Kind.AND, temp, s.mkTerm(Kind.NOT, (encode_is_null(names[i], types[i]))))

        return temp

    raise ValueError(f"Unsupported type: {key}")


# modified version of encode_expr, main goal is to find all smallest unit of expressions that are columns 
def encode_nulls_helper(schema, idx, expr, variables):
    global s, q1_alias_map, q2_alias_map
    if (idx == 1): 
        alias_map = q1_alias_map
    elif (idx == 2):
        alias_map = q2_alias_map
    # literals
    if isinstance(expr, exp.Literal):
        # do nothing
        return [], []

    names, types = [], []
    if isinstance(expr, exp.Condition):
        key = expr.key.lower()
        if key in ["add", "sub", "mul"]:
            left, right = expr.args["this"], expr.args["expression"]
            lnames, ltypes = encode_nulls_helper(schema, idx, left, variables)
            rnames, rtypes = encode_nulls_helper(schema, idx, right, variables)
            names.extend(lnames)
            names.extend(rnames)
            types.extend(ltypes)
            types.extend(rtypes)
             
    if isinstance(expr, exp.Column):
        table = alias_map[str(expr.table)]
        column = str(expr.this)
        names = [variables[table][column]]
        types = [schema[table][column]]
    
    return names, types

    

def encode_left_join(on_pred, left_row, right_row, Join):
    global s, NULL
    join_call = s.mkTerm(Kind.APPLY_UF, Join, left_row, right_row)
    return s.mkTerm(Kind.AND, 
        s.mkTerm(Kind.NOT, (encode_is_null(left_row, "INT"))), #left key is not null
        s.mkTerm(Kind.IMPLIES, on_pred, join_call),
        s.mkTerm(Kind.IMPLIES, s.mkTerm(Kind.NOT, on_pred), s.mkTerm(Kind.APPLY_UF, Join, left_row, NULL)),
        # s.mkTerm(Kind.IMPLIES, join_call, on_pred)
    )

def encode_full_join(on_pred, left_row, right_row, Join):
    global s, NULL
    join_call = s.mkTerm(Kind.APPLY_UF, Join, left_row, right_row)
    return s.mkTerm(Kind.AND, 
        s.mkTerm(Kind.IMPLIES, on_pred, join_call),
        s.mkTerm(Kind.IMPLIES, s.mkTerm(Kind.NOT, on_pred), 
                 s.mkTerm(Kind.APPLY_UF, Join, left_row, NULL), 
                 s.mkTerm(Kind.APPLY_UF, Join, NULL, right_row)),
        # s.mkTerm(Kind.IMPLIES, join_call, on_pred) 
    )
    

# add constraints for simple WHERE clauses like 'R.age > 20' or 'T.id = 3'.
def encode_where(schema, ast, idx, variables):
    where = ast.args.get("where")
    if not where:
        return s.mkTrue()

    expr = where.this
    encoding = encode_condition(schema, expr, idx, variables)
    # print(f"line414, type of encoding = {type(encoding)}")
    encoding = encode_nulls(schema, expr, idx, encoding)
    return encoding


def encode_condition(schema, expr, idx, variables, join=False):
    # print(f"line314, encode_condition({expr}) in query{idx}")
    global s, vars
    key = expr.key.lower()

    # for now, we're only handling simple comparisons: <, >, =, <=, >=
    # and, or, not, (IS NULL / IS NOT NULL)
    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(schema, idx, left, right, key, variables)
            if constraint is not None:
                return constraint
        elif key == "and":
            return s.mkTerm(Kind.AND, encode_condition(schema, expr.args["this"], idx, variables),
                   encode_condition(schema, expr.args["expression"], idx, variables))
        elif key == "or":
            return s.mkTerm(Kind.OR, encode_condition(schema, expr.args["this"], idx, variables),
                   encode_condition(schema, expr.args["expression"], idx, variables))
        elif key == "not":
            return s.mkTerm(Kind.NOT, (encode_condition(schema, expr.args["this"], idx, variables)))
        elif key == "is":
            name, type = encode_expr(schema, idx, expr.this, vars)
            # print(f"line397, query{idx}, name = {name}")
            return encode_is_null(name, type)

    exit(f"Unsupported type: {key}")



# convert a simple comparison expression to a Z3 constraint
def encode_comparison(schema, idx, left, right, op, variables):
    # print(f"line355, encode_comparison({left}, {op}, {right}) in query{idx}")
    left, ltype = encode_expr(schema, idx, left, variables)
    right, rtype = encode_expr(schema, idx, right, variables)

    if op == "gt":
        return s.mkTerm(Kind.GT, left, right)
    elif op == "lt":
        return s.mkTerm(Kind.LT, left, right)
    elif op == "gte":
        return s.mkTerm(Kind.GEQ, left, right)
    elif op == "lte":
        return s.mkTerm(Kind.LEQ, left, right)
    elif op == "eq":
        # STAR! 
        # this is a special check that exists in cvc5 but not in Z3
        # when operation is "=", the type of both sides need to be equivalent
        # initially I was thinking of treating all integers and reals as reals
        # but then we will get different output for queries like:
            # SELECT * FROM Students WHERE Students.id > 1.0 AND Students.id < 2.0;
        if ltype != rtype:
            raise ValueError(f"Type mismatch in EQUAL comparison in query{idx}. Expected both sides to have the same type, but got: {ltype} vs {rtype}")
        return s.mkTerm(Kind.EQUAL, left, right)

    return s.mkFalse()


# encode IS NULL conditions
def encode_is_null(col_name, col_type="INT"):
    global null_funcs, s 

    if col_type == "INT":
        fn = null_funcs[0]
    elif col_type == "STRING":
        fn = null_funcs[1]   
    else:  # col_type == "REAL"
        fn = null_funcs[2]     

    # apply the uninterpreted function: NullX(col_name)
    return s.mkTerm(Kind.APPLY_UF, fn, col_name)


# # todo
# # encode DISTINCT for primary key and that in select clause
# def encode_is_distinct(col_name, col_type="INT"):
#     # print(f"line462, col_name is {col_name}")
#     global distinct_funcs, vars
#     if col_type == "INT":
#         return distinct_funcs[0](col_name)
#     elif col_type =="STRING":
#         return distinct_funcs[1](col_name)
#     else: #col_type == "REAL"
#         return distinct_funcs[2](col_name)


 
# returns a tuple (expr, type), where expr is a cvc5.Term
def encode_expr(schema, idx, expr, variables):
    # print(f"line473, encode_expr({expr}) in query{idx}")
    global q1_alias_map, q2_alias_map, q1_used_terms, q2_used_terms, vars
    if (idx == 1): 
        alias_map, used_terms = q1_alias_map, q1_used_terms
    elif (idx == 2):
        alias_map, used_terms = q2_alias_map, q2_used_terms

    # literals
    if isinstance(expr, exp.Literal):
        if expr.is_int:
            return s.mkInteger(int(expr.this)), "INT"
        if expr.is_number:
            return s.mkReal(expr.this), "REAL"
        if expr.is_string:
            return s.mkString(expr.this), "STRING"
        else:
            exit(f"unknown type for {expr}")

    if isinstance(expr, exp.Condition):
        key = expr.key.lower()
        # handle math ops
        if key in ["add", "sub", "mul"]:
            left, right = expr.args["this"], expr.args["expression"]
            left, ltype = encode_expr(schema, idx, left, variables)
            right, rtype = encode_expr(schema, idx, right, variables)
            
            if (ltype == "STRING" or rtype == "STRING"):
                exit("cannot perform arithematic operation on String type")
            if not (ltype in ["INT", "REAL"] and rtype in ["INT", "REAL"]):
                exit(f"type mismatch between {ltype} and {rtype}")

            # another modification
            if (ltype == "REAl" or rtype == "REAL") and not (ltype == "REAl" and rtype == "REAL") :
                ltype = "REAL"
            
            if key == "add":
                return s.mkTerm(Kind.ADD, left, right), ltype
            elif key == "sub":
                return s.mkTerm(Kind.SUB, left, right), ltype
            elif key == "mul":
                return s.mkTerm(Kind.MULT, left, right), ltype
            else:
                raise ValueError(f"Unsupported math operation {key}")
   
    if isinstance(expr, exp.Column):
        table = alias_map[str(expr.table)]
        column = str(expr.this)
        used_terms.add(vars[table][column])
        return variables[table][column], schema[table][column]
    
    raise Exception(f"encode_expr: could not resolve {expr} in query{idx}")
    # exit(f"encode_expr: could not resolve {expr} in query{idx}")


def encode_not_null_for_primary_keys(schema, idx):
    global s, vars, not_null, q1_used_terms, q2_used_terms
    if idx == 1:
        used_terms = q1_used_terms
    else:
        used_terms = q2_used_terms
    # print(f"line535, used terms in query{idx} are: {used_terms}")

    temp = s.mkTrue()
    for table_name in not_null:
        ls = not_null[table_name]
        for col_name in ls :
            if table_name in vars:
                col_name, col_type = vars[table_name][col_name], schema[table_name][col_name]
                if col_name not in used_terms:
                    temp = s.mkTerm(Kind.AND, temp, s.mkTerm(Kind.NOT, encode_is_null(col_name, col_type)))
    return temp 


def exit(err_message):
    print(err_message)
    sys.exit(1)