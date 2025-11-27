import sys
import sqlglot
from sqlglot import parse_one


# parse schema manually
def parse_schema(schema_path):
    with open(schema_path) as f:
        schema_sql = f.read()
    schema = {}
    not_null = {}
    primary_keys = {}
    lines = schema_sql.split(";")
   
    sql_data_types = { 
        "INT": "INT", 
        "INTEGER": "INT", 
        "TEXT": "STRING",
        "REAL": "REAL"
    }
    for stmt in lines:
        stmt = stmt.strip()
        if stmt.lower().startswith("create table"):
            name = stmt.split()[2]
            cols = stmt[stmt.find("(")+1 : stmt.find(")")].split(",")
            schema[name] = {}
            not_null[name] = []
            for c in cols:
                ls = c.strip().split()
                cname, ctype = ls[0:2]
                ctype = ctype.upper()

                if (len(ls) == 4):
                    if ((ls[2].upper() == "NOT" and ls[3].upper() == "NULL") or 
                        (ls[2].upper() == "PRIMARY" and ls[3].upper() == "KEY")) :
                        not_null[name].append(cname)
                        if (ls[2].upper() == "PRIMARY" and ls[3].upper() == "KEY") :
                            primary_keys[name] = cname
                
                if (ctype not in sql_data_types): 
                    print("Type", ctype, "is not supported")
                    sys.exit(1)
                schema[name][cname] = sql_data_types[ctype]
    return schema, not_null, primary_keys


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
