import sys
import sqlglot
from sqlglot import errors, parse_one


# parse schema manually
def parse_schema(schema_path):
    with open(schema_path) as f:
        schema_sql = f.read()
    schema = {}
    lines = schema_sql.split(";")
   
    sql_data_types = {   # todo: update this dict 
        "INT": "INT", 
        "INTEGER": "INT", 
        "TEXT": "STRING",
        "REAL": "REAL"
        # "VARCHAR": "STRING" 
    }
    for stmt in lines:
        stmt = stmt.strip()
        if stmt.lower().startswith("create table"):
            name = stmt.split()[2]
            cols = stmt[stmt.find("(")+1 : stmt.find(")")].split(",")
            schema[name] = {}
            for c in cols:
                cname, ctype = c.strip().split()
                ctype = ctype.upper()
                if (ctype not in sql_data_types): 
                    print("Type", ctype, "is not supported")
                    sys.exit(1)
                schema[name][cname] = sql_data_types[ctype]
    return schema


# use sqlglot to parse queries
def parse_query(query_path):
    with open(query_path) as f: 
        query_sql = f.read()
    
    try:
        ast = sqlglot.transpile(query_sql)
    except sqlglot.errors.ParseError as e:
        print(e.errors)
        sys.exit(1)

    if len(ast) != 1: 
        print("There should be exactly one query in", query_path)
        sys.exit(1)

    ast = parse_one(query_sql)
    return ast
