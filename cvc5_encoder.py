import sys
from sqlglot import expressions as exp
import cvc5
from cvc5 import Kind


def encode(sch, q1_ast, q2_ast, map1, map2, c2t, c2t2, nn):
    # step 0: read inputs, define and initialize global variables
    global s, q1_alias_map, q2_alias_map, q1_col2tables, q2_col2tables, vars, schema, not_nulls, COUNT
    global q1_agg_output, q2_agg_output, q1_select_out, q2_select_out
    
    s = cvc5.Solver()
    s.setLogic("ALL") 
    s.setOption("produce-models", "true")
    s.setOption("produce-unsat-cores", "true")

    q1_alias_map, q2_alias_map, q1_col2tables, q2_col2tables, schema, not_nulls = map1, map2, c2t, c2t2, sch, nn
    q1_agg_output, q2_agg_output = None, None
    q1_select_out, q2_select_out = [], []

    # step 1: declare variables
    vars = declare_variables()

    # step 2: encode constraints for each query
    encode_query(q1_ast, idx=1)
    encode_query(q2_ast, idx=2)

    # step 3:
    s.assertFormula(encode_diff())

    # step 4: (extra step that is not required in z3) list all variables we want to get values of, if the problem is sat
    variables_to_interpret = extract_values(vars.values())
    return s, variables_to_interpret 


def extract_values(nested):
    variables_to_interpret = set()
    for block in nested:
        if isinstance(block, dict):
            for _, term in block.items():
                variables_to_interpret.add(term)
        else: 
            symbol = block.getSymbol()
            if (symbol.startswith("q1_") or symbol.startswith("q2_")) and symbol.endswith("_result"):
                variables_to_interpret.add(block)
            elif symbol in ["q1_after_match", "q2_after_match", "q1_after_right_null", 
                          "q2_after_right_null", "q1_after_left_null",  "q2_after_left_null"]:
                variables_to_interpret.add(block)
    return variables_to_interpret

def encode_diff():
    global s, q1_where_vars, q2_where_vars
    global q1_agg_output, q2_agg_output
    global q1_select_out, q2_select_out

    Or  = lambda *xs: s.mkTerm(Kind.OR, *xs)
    And = lambda *xs: s.mkTerm(Kind.AND, *xs)
    Not = lambda x: s.mkTerm(Kind.NOT, x)
    Eq  = lambda x, y: s.mkTerm(Kind.EQUAL, x, y)

    diffs = [
        Not(Eq(q1_where_vars["after_match"], q2_where_vars["after_match"])),
        Not(Eq(q1_where_vars["after_rnull"],  q2_where_vars["after_rnull"])),
        Not(Eq(q1_where_vars["after_lnull"],  q2_where_vars["after_lnull"])),
    ]

    if q1_agg_output is not None or q2_agg_output is not None:
        if q1_agg_output is None or q2_agg_output is None:
            diffs.append(s.mkTrue())
            return Or(*diffs)

        if isinstance(q1_agg_output, tuple):
            num1, den1 = q1_agg_output
            num2, den2 = q2_agg_output

            diffs.append(Not(Eq(num1, num2)))
            diffs.append(Not(Eq(den1, den2)))
            return Or(*diffs)

        diffs.append(Not(Eq(q1_agg_output, q2_agg_output)))
        return Or(*diffs)

    if q1_select_out and q2_select_out:
        for (v1, n1), (v2, n2) in zip(q1_select_out, q2_select_out):
            diffs.append(
                And(
                    q1_where_vars["after_match"],
                    q2_where_vars["after_match"],
                    Or(Not(Eq(v1, v2)), Not(Eq(n1, n2)))
                )
            )

    return Or(*diffs)


# declare Z3 variables for all attributes in all tables
# returns a map, which maps dict[table][column] -> Z3 variable
def declare_variables():  
    global not_nulls, schema
    variables = {}
    variables["present"] = {}

    for table in schema.keys():        
        variables["present"][table] =  s.mkConst(s.getBooleanSort(), f"{table}_present")

    for table in schema.keys():
        variables[table] = {}
        for column, col_type in schema[table].items():
            var_name = f"{table}_{column}"
            if col_type == "INT":
                variables[table][column] = s.mkConst(s.getIntegerSort(), var_name)
            elif col_type =="STRING":
                variables[table][column] = s.mkConst(s.getStringSort(), var_name)
            else: #col_type == "REAL"
                variables[table][column] = s.mkConst(s.getRealSort(), var_name)
            # add 'is_null' flags for every attribute
            if table in not_nulls and column in not_nulls[table]:
                variables[table][f"{column}_is_null"] = s.mkFalse()
            else:
                variables[table][f"{column}_is_null"] =  s.mkConst(s.getBooleanSort(), f"{table}_{column}_is_null")
    
    return variables


def encode_query(ast, idx):
    join_type = encode_join(ast, idx)
    encode_where(ast, idx, join_type)
    encode_select(ast, idx)


def encode_where(ast, idx, join_type):
    if idx == 1:
        global q1_join_vars, s
        join_vars = q1_join_vars
    else:
        global q2_join_vars, s
        join_vars = q2_join_vars

    # create after-where booleans
    q_after_match      = s.mkConst(s.getBooleanSort(), f"q{idx}_after_match")
    q_after_right_null = s.mkConst(s.getBooleanSort(), f"q{idx}_after_right_null")
    q_after_left_null  = s.mkConst(s.getBooleanSort(), f"q{idx}_after_left_null")

    where = ast.args.get("where")
    if where:
        cond_where = encode_condition(where.this, idx, where=True)
    else: 
        cond_where = s.mkTrue()
    
    # no join --> single row only
    if join_type == "no_join":
        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_match, cond_where))
        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_right_null, s.mkFalse()))
        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_left_null, s.mkFalse()))
    else :
        # get the actual join variables created earlier
        q_match      = join_vars["match"]
        q_right_null = join_vars["rnull"]
        q_left_null  = join_vars["lnull"]

        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_match, s.mkTerm(Kind.AND, q_match, cond_where)))
        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_right_null, s.mkTerm(Kind.AND, q_right_null, cond_where)))
        s.assertFormula(s.mkTerm(Kind.EQUAL, q_after_left_null, s.mkTerm(Kind.AND, q_left_null, cond_where)))

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



def encode_select(ast, idx):
    """
    Encodes the SELECT clause, handling COUNT(*) aggregates and regular projections.
    """
    global s, q1_select_out, q2_select_out, q1_agg_output, q2_agg_output
    global q1_where_vars, q2_where_vars, s, vars, schema, q1_alias_map, q2_alias_map

    Or  = lambda *args: s.mkTerm(Kind.OR, *args)
    And = lambda *args: s.mkTerm(Kind.AND, *args)
    Not = lambda x: s.mkTerm(Kind.NOT, x)
    Eq  = lambda x, y: s.mkTerm(Kind.EQUAL, x, y)

    select_exprs = ast.args.get("expressions")
    outputs = []

    
    # Default SELECT * if no expressions given
    if select_exprs is None:
        select_exprs = [exp.Star()]

    for expr in select_exprs:
        # Aliases: extract actual expression first
        if isinstance(expr, exp.Alias):
            expr = expr.this

        # --- COUNT(*) AGGREGATE ---
        if is_count_star(expr):
            where_vars = get_where_vars(idx)
            row_exists = get_row_existence_condition(idx, where_vars)
            count_val = s.mkConst(s.getIntegerSort(), f"q{idx}_count_star_result")

            # count = 1 if row exists, else 0
            s.assertFormula(s.mkTerm(Kind.EQUAL, 
                                     count_val, 
                                     s.mkTerm(Kind.ITE, row_exists, s.mkInteger(1), s.mkInteger(0))))

            if idx == 1:
                q1_agg_output = count_val
            else:
                q2_agg_output = count_val

            continue
        # --- END COUNT(*) ---

        # --- COUNT(col) ---
        if is_count_col(expr):
            where_vars = get_where_vars(idx)
            row_exists = get_row_existence_condition(idx, where_vars)

            # Extract the column expression
            col_expr = extract_aggregate_column(expr)

            # Use encode_expr to get the joined (post-WHERE) value + null flag
            _, _, nulls = encode_expr(idx, col_expr, where=True)
            nulls.append(s.mkFalse())
            nulls.append(s.mkFalse())
            col_is_null = Or(*nulls) 

            count_val = s.mkConst(s.getIntegerSort(), f"q{idx}_count_col_result")

            # COUNT(col) counts only NOT NULL values
            s.assertFormula(s.mkTerm(Kind.EQUAL, 
                                     count_val, 
                                     s.mkTerm(Kind.ITE, And(row_exists, Not(col_is_null)), s.mkInteger(1), s.mkInteger(0))))

            if idx == 1:
                q1_agg_output = count_val
            else:
                q2_agg_output = count_val

            continue
        # --- END COUNT(col) ---
        

        # --- SUM(col) ---
        if is_sum_col(expr):
            where_vars = get_where_vars(idx)
            row_exists = get_row_existence_condition(idx, where_vars)

            # Get the column expression
            col_expr = extract_aggregate_column(expr)

            # Use encode_expr to get column value + null flag
            col_val, col_type, nulls = encode_expr(idx, col_expr, where=True)
            nulls.append(s.mkFalse())
            nulls.append(s.mkFalse())
            col_is_null = Or(*nulls) 

            # SUM(col) = col_val IF row exists AND col is non-null, else 0
            # In cvc5, both THEN ELSE branch must have the same type, so it fails when there's SUM(some_real_attribute_like_GPA)
            if col_type == "STRING": 
                exit(f"The SUM() aggregate function in SQL is designed to work with numeric data types, but get STRING")
            elif col_type == "INT":
                null_value = s.mkInteger(0)
                sum_val = s.mkConst(s.getIntegerSort(), f"q{idx}_sum_col_result")
            else:
                null_value = s.mkReal(0)
                sum_val = s.mkConst(s.getRealSort(), f"q{idx}_sum_col_result")

            s.assertFormula(s.mkTerm(Kind.EQUAL, 
                                     sum_val, 
                                     s.mkTerm(Kind.ITE, And(row_exists, Not(col_is_null)), col_val, null_value)))

            # store as the aggregate output (same mechanism as COUNT)
            if idx == 1:
                q1_agg_output = sum_val
            else:
                q2_agg_output = sum_val

            continue
        # --- END SUM(col) ---

        # --- AVG(col) ---
        if is_avg_col(expr):
            where_vars = get_where_vars(idx)
            row_exists = get_row_existence_condition(idx, where_vars)

            # Extract the column expression
            col_expr = extract_aggregate_column(expr)

            # Encode the column value, type, and nulls
            col_val, col_type, nulls = encode_expr(idx, col_expr, where=True)
            col_is_null = Or(*nulls) if nulls else s.mkFalse()

            # Create numerator and denominator variables
            avg_den = s.mkConst(s.getIntegerSort(), f"q{idx}_avg_den")

            # AVG semantics:
            # numerator = SUM(col) over non-null values
            # denominator = COUNT(col) over non-null values
            # same here, don't hardcode type
            if col_type == "STRING": 
                exit(f"The AVG() aggregate function in SQL is designed to work with numeric data types, but get STRING")
            elif col_type == "INT":
                avg_num = s.mkConst(s.getIntegerSort(), f"q{idx}_avg_num")
                null_value = s.mkInteger(0)
            else:
                avg_num = s.mkConst(s.getRealSort(), f"q{idx}_avg_num")
                null_value = s.mkReal(0)

            s.assertFormula(s.mkTerm(Kind.EQUAL, 
                                     avg_num, 
                                     s.mkTerm(Kind.ITE, And(row_exists, Not(col_is_null)), col_val, null_value)))
            s.assertFormula(s.mkTerm(Kind.EQUAL, 
                                     avg_den, 
                                     s.mkTerm(Kind.ITE, And(row_exists, Not(col_is_null)), s.mkInteger(1), s.mkInteger(0))))


            # Store as aggregate output as a tuple-like structure
            if idx == 1:
                q1_agg_output = (avg_num, avg_den)
            else:
                q2_agg_output = (avg_num, avg_den)

            continue
        # --- END AVG(col) ---

        # Handle STAR (expand all columns)
        if isinstance(expr, exp.Star):
            if idx == 1:
                alias_map = q1_alias_map
            else: 
                alias_map = q2_alias_map
            for aliased_table_name, real_table_name in alias_map.items():
                for col in schema[real_table_name]:
                    v = vars[f"J{idx}_{real_table_name}_{col}"]
                    n = vars[f"J{idx}_{real_table_name}_{col}_is_null"]
                    outputs.append((v, n))
            continue

        # Regular expression output
        val, _, nulls = encode_expr(idx, expr, where=True)
        if not nulls: 
            return s.mkFalse()
        elif len(nulls) == 1: 
            null_flag = nulls[0]
        else:
            null_flag = Or(*nulls)
        outputs.append((val, null_flag))

    # Assign outputs to global structure
    if idx == 1:
        q1_select_out = outputs
    else:
        q2_select_out = outputs



def is_count_star(expr):
    """
    Matches COUNT(*) pattern in sqlglot AST:
      exp.Count(this=exp.Star())
    """
    if isinstance(expr, exp.Count):
        return isinstance(expr.this, exp.Star)
    # Also handle Anonymous case for backwards compatibility
    if isinstance(expr, exp.Anonymous):
        if expr.this.lower() == "count":
            args = expr.expressions or []
            return len(args) == 1 and isinstance(args[0], exp.Star)
    return False


def is_count_col(expr):
    """
    Detects COUNT(col) where col is a column reference.
    Does NOT match COUNT(*) or COUNT(<expr>) for now.
    """
    # Pattern: Count(this=Column)
    if isinstance(expr, exp.Count):
        return isinstance(expr.this, exp.Column)
    # Pattern: Anonymous function: count(col)
    if isinstance(expr, exp.Anonymous):
        if expr.this.lower() == "count":
            args = expr.expressions or []
            return len(args) == 1 and isinstance(args[0], exp.Column)
    return False


def is_sum_col(expr):
    """
    Detects SUM(col) where col is a direct column reference.
    Does NOT handle SUM(*) or SUM(expr) yet.
    """
    if isinstance(expr, exp.Sum):
        return isinstance(expr.this, exp.Column)
    if isinstance(expr, exp.Anonymous):
        if expr.this.lower() == "sum":
            args = expr.expressions or []
            return len(args) == 1 and isinstance(args[0], exp.Column)
    return False


def extract_aggregate_column(expr):
    """
    Extracts the column expression from aggregate functions like COUNT(col), SUM(col), AVG(col).
    Works with both native sqlglot expressions and Anonymous function calls.
    """
    if isinstance(expr, (exp.Count, exp.Sum, exp.Avg)):
        return expr.this
    if isinstance(expr, exp.Anonymous):
        args = expr.expressions or []
        if len(args) == 1:
            return args[0]
    return None


def get_row_existence_condition(idx, where_vars):
    """
    Returns a Z3 expression representing whether a row exists after WHERE clause.
    A row exists if it's in any of: after_match, after_rnull, or after_lnull.
    """
    return s.mkTerm(Kind.OR, 
        where_vars["after_match"],
        where_vars["after_rnull"],
        where_vars["after_lnull"]
    )

def get_where_vars(idx):
    """
    Returns the appropriate where_vars dictionary for the given query index.
    """
    global q1_where_vars, q2_where_vars
    return q1_where_vars if idx == 1 else q2_where_vars


def is_avg_col(expr):
    """
    Detects AVG(col) where col is a direct column reference.
    Does NOT handle AVG(*) or AVG(expr) yet.
    """
    if isinstance(expr, exp.Avg):
        return isinstance(expr.this, exp.Column)
    if isinstance(expr, exp.Anonymous):
        if expr.this.lower() == "avg":
            args = expr.expressions or []
            return len(args) == 1 and isinstance(args[0], exp.Column)
    return False



def encode_condition(expr, idx, where=False):
    key = expr.key.lower()

    if isinstance(expr, exp.Condition):
        if key in ["gt", "lt", "gte", "lte", "eq", "neq"]:
            left, right = expr.args["this"], expr.args["expression"]
            constraint = encode_comparison(idx, left, right, key, where)
            if constraint is not None:
                return constraint
        elif key == "and":
            return s.mkTerm(Kind.AND, encode_condition(expr.args["this"], idx, where),
                   encode_condition(expr.args["expression"], idx, where))
        elif key == "or":
            return s.mkTerm(Kind.OR, encode_condition(expr.args["this"], idx, where),
                   encode_condition(expr.args["expression"], idx, where))
        elif key == "not": # (T.sid IS NOT NULL) is parsed as (NOT T.sid IS NULL)
            return s.mkTerm(Kind.NOT, (encode_condition(expr.args["this"], idx, where)))
        elif key == "is":
            _, _, col_is_null = encode_expr(idx, expr.this, where)              
            return col_is_null[0]
    exit(f"Unsupported type: {key}")



def encode_comparison(idx, left, right, op, where):
    # print(f"line174, encode_comparison(left = {left}, right = {right})")
    left, ltype, lcols = encode_expr(idx, left, where)
    right, rtype, rcols = encode_expr(idx, right, where)

    left_null  = s.mkTerm(Kind.OR, s.mkFalse(), s.mkFalse(), *lcols)  # added an additional false just in case len(lcols) = 0
    right_null = s.mkTerm(Kind.OR, s.mkFalse(), s.mkFalse(), *rcols)

    return sql_cmp_base(idx, left, left_null, right, right_null, ltype, rtype, op)


def sql_cmp_base(idx, left_val, left_null, right_val, right_null, ltype, rtype, op):
    both_not_null = s.mkTerm(Kind.AND, s.mkTerm(Kind.NOT, left_null), s.mkTerm(Kind.NOT, right_null))
    if op == "eq":     # =
        # STAR! 
        # this is a special check that exists in cvc5 but not in Z3
        # when operation is "=", the type of both sides need to be equivalent
        # initially I was thinking of treating all integers and reals as reals
        # but then we will get different output for queries like:
            # SELECT * FROM Students WHERE Students.id > 1.0 AND Students.id < 2.0;
        # print(f"left = {left_val}, type = {ltype}")
        # print(f"right = {right_val}, type = {rtype}")
        if ltype != rtype:
            exit(f"Type mismatch in EQUAL comparison in query{idx}. Expected both sides to have the same type, but got: {ltype} vs {rtype}")
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.EQUAL, left_val, right_val))
    elif op == "neq":  # <> 
        # same for neq
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.NOT, s.mkTerm(Kind.EQUAL, left_val, right_val)))
    elif op == "gt":   # >
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.GT, left_val, right_val))
    elif op == "lt":   # <
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.LT, left_val, right_val))
    elif op == "gte":  # >=
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.GEQ, left_val, right_val))
    elif op == "lte":  # <=
        return s.mkTerm(Kind.AND, both_not_null, s.mkTerm(Kind.LEQ, left_val, right_val))
    else:
        exit(f"Unknown comparison op: {op}")


def encode_expr(idx, expr, where=False):
    # literals
    if isinstance(expr, exp.Literal):
        if expr.is_int:
            return s.mkInteger(int(expr.this)), "INT", []
        if expr.is_number:
            return s.mkReal(expr.this), "REAL", []
        if expr.is_string:
            return s.mkString(expr.this), "STRING", []
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

            # another modification
            if (ltype == "REAl" or rtype == "REAL") and not (ltype == "REAl" and rtype == "REAL") :
                ltype = "REAL"
            
            if key == "add":
                return s.mkTerm(Kind.ADD, left, right), ltype, lcols + rcols
            elif key == "sub":
                return s.mkTerm(Kind.SUB, left, right), ltype, lcols + rcols
            elif key == "mul":
                return s.mkTerm(Kind.MULT, left, right), ltype, lcols + rcols
            else:
                raise ValueErrs.mkTerm(Kind.OR,  f"Unsupported math operation {key}")
   
    if isinstance(expr, exp.Column):
        table = get_table(idx, expr)
        column = str(expr.this)
        if not where:
            return vars[table][column], schema[table][column], [vars[table][f"{column}_is_null"]]
        else:
            return vars[f"J{idx}_{table}_{column}"], schema[table][column], [vars[f"J{idx}_{table}_{column}_is_null"]]
    
    raise Exception(f"encode_expr: could not resolve {expr} in query{idx}")


def get_table(idx, expr): # expr is guaranteed to be an instance of exp.Column
    if expr.table:
        global q1_alias_map, q2_alias_map
        if (idx == 1): 
            alias_map = q1_alias_map
        elif (idx == 2):
            alias_map = q2_alias_map
        return alias_map[str(expr.table)]
    else: 
        global q1_col2tables, q2_col2tables
        if (idx == 1): 
            col2tables = q1_col2tables
        elif (idx == 2):
            col2tables = q2_col2tables
        return col2tables[str(expr.this)][0]


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
                val = s.mkConst(s.getIntegerSort(), var_name)
            elif type == "REAL":
                val = s.mkConst(s.getRealSort(), var_name)
            else:
                val = s.mkConst(s.getStringSort(), var_name)

            # null flag variable for query idx
            null_name = f"J{idx}_{table}_{col}_is_null"
            is_null = s.mkConst(s.getBooleanSort(), null_name)

            vars[f"J{idx}_{table}_{col}"] =  val
            vars[f"J{idx}_{table}_{col}_is_null"] = is_null


def encode_join(ast, idx):
    # pick which query (q1 or q2)
    if idx == 1:
        global q1_alias_map, vars, s
        alias_map  = q1_alias_map
        allocate_join_result_vars(idx=1)
    else:
        global q2_alias_map, vars, s
        alias_map  = q2_alias_map
        allocate_join_result_vars(idx=2)

    # produce NEW join booleans for this query
    q_match      = s.mkConst(s.getBooleanSort(), f"q{idx}_match")
    q_right_null = s.mkConst(s.getBooleanSort(), f"q{idx}_right_null")
    q_left_null  = s.mkConst(s.getBooleanSort(), f"q{idx}_left_null")
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
    left_table_name, right_table_name, jtype = get_join_tables_and_type(ast, joins)

    if jtype == "no_join":
        encode_join_result(idx, left_table_name, right_table_name, jtype)
    else: 
        # resolve real table names (consider alias)
        left_real  = alias_map.get(left_table_name, left_table_name)
        right_real = alias_map.get(right_table_name, right_table_name)

        left_present  = vars["present"][left_real]
        right_present = vars["present"][right_real]

        # handle cartesian product
        if jtype == "CP":
            encode_cartisian_product(left_present, right_present, q_match, q_right_null, q_left_null)
        else: 
            # compute ON predicate
            join = joins[0]
            cond = join.args.get("on")
            on_pred = encode_condition(cond, idx)

            # join type handlers
            if jtype == "INNER":
                encode_inner_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null)
            elif jtype == "LEFT":
                encode_left_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null, right_table_name)
            elif jtype == "RIGHT":
                encode_left_join(on_pred, right_present, left_present, q_match, q_right_null, q_left_null, left_table_name)
            elif jtype == "FULL":
                encode_full_join(on_pred, left_present, right_present, q_match, q_left_null, q_right_null, left_table_name, right_table_name)
            else:
                raise ValueErrs.mkTerm(Kind.OR,  f"Unknown join type {jtype}")
        
        encode_join_result(idx, left_real, right_real, jtype)

    return jtype


def encode_cartisian_product(left_present, right_present, q_match, q_right_null, q_left_null):
    global s
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_match, s.mkTerm(Kind.AND, left_present, right_present)))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_right_null, s.mkFalse()))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_left_null, s.mkFalse()))


def encode_inner_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null):
    global s
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_match, s.mkTerm(Kind.AND, s.mkTerm(Kind.AND, left_present, right_present), on_pred)))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_right_null, s.mkFalse()))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_left_null, s.mkFalse()))
    

def encode_left_join(on_pred, left_present, right_present, q_match, q_right_null, q_left_null, right_table):
    global s
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_match, s.mkTerm(Kind.AND, s.mkTerm(Kind.AND, left_present, right_present), on_pred)))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_right_null, s.mkTerm(Kind.AND, left_present, s.mkTerm(Kind.NOT, on_pred))))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_left_null, s.mkFalse()))


def encode_full_join(on_pred, left_present, right_present, q_match, q_left_null, q_right_null, left_table, right_table):
    global s
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_match, s.mkTerm(Kind.AND, s.mkTerm(Kind.AND, left_present, right_present), on_pred)))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_right_null, s.mkTerm(Kind.AND, left_present, s.mkTerm(Kind.NOT, on_pred))))
    s.assertFormula(s.mkTerm(Kind.EQUAL, q_left_null, s.mkTerm(Kind.AND, right_present, s.mkTerm(Kind.NOT, on_pred))))


def encode_join_result(idx, left_table, right_table, join_type):
    global s, vars, schema, q1_join_vars, q2_join_vars
    if (idx == 1): 
        match, left_null, right_null = q1_join_vars["match"], q1_join_vars["lnull"], q1_join_vars["rnull"]
    else: 
        match, left_null, right_null = q2_join_vars["match"], q2_join_vars["lnull"], q2_join_vars["rnull"]
    
    def null_literal(type):
        if type == "INT": return s.mkConst(s.getIntegerSort(), "NULL_INT") 
        if type == "REAL": return s.mkConst(s.getRealSort(), "NULL_REAL") 
        return s.mkConst(s.getStringSort(), "NULL_STRING") 

    for table, columns in schema.items():
        if join_type == "no_join": 
            use_base = s.mkTrue()
        elif join_type == "INNER" or join_type == "CP":
            use_base = match

        elif join_type == "LEFT":
            if table == left_table:
                use_base = s.mkTerm(Kind.OR,  match, right_null)
            else:
                use_base = match

        elif join_type == "RIGHT":
            if table == right_table:
                use_base = s.mkTerm(Kind.OR,  match, left_null)
            else:
                use_base = match

        elif join_type == "FULL":
            if table == left_table:
                use_base = s.mkTerm(Kind.OR,  match, right_null)
            else:
                use_base = s.mkTerm(Kind.OR,  match, left_null)

        for col, ctype in columns.items():
            base_val   = vars[table][col]
            base_is_null = vars[table][f"{col}_is_null"]

            J_val  = vars[f"J{idx}_{table}_{col}"]
            J_null = vars[f"J{idx}_{table}_{col}_is_null"]

            null_val = null_literal(ctype)
            
            s.assertFormula(s.mkTerm(Kind.EQUAL, J_val, s.mkTerm(Kind.ITE,  use_base, base_val,  null_val)))
            s.assertFormula(s.mkTerm(Kind.EQUAL, J_null, s.mkTerm(Kind.ITE,  use_base, base_is_null, s.mkTrue())))


def encode_cols_null(table):
    global s, schema, vars
    cols_is_null = s.mkTrue()
    for column, _ in schema[table].items():
        cols_is_null = s.mkTerm(Kind.AND, cols_is_null, vars[table][f"{column}_is_null"])
    return cols_is_null



def exit(err_message):
    print(err_message)
    sys.exit(1)