# EquiSQL

EquiSQL is a lightweight SQL query equivalence checker that uses SMT solving to reason about whether two SQL queries are semantically equivalent.  It parses SQL queries, converts them into logical formulas, and invokes the Z3 solver to search for counterexamples—cases where the queries return different results.

## Current Features
- Supports a small subset of SQL (e.g. `SELECT`, `FROM`, `WHERE`), single table, no table aliasing
- Supports simple conjunction, disconjuction, and arithematic logic
- Supports simple arithematic operations such as add, minus, and multiplication
- Support explicit and implicit INNER and OUTER JOINs
- Allows use of table aliases
- Support `IS NULL` and `IS NOT NULL` conditions, and recognizes attributes declared as NOT NULL in table definitions
- Support `LIMIT` and `OFFSET` clauses
- Translates queries into logical constraints for Z3
- Reports counterexamples when queries differ

## Example usage
command line (check more examples in note.txt): 
python main.py test/create-table.sql test/query1.sql test/query2.sql


## What we will explore next
- Integrate additional SMT solvers such as CVC5


For more details on ongoing process, check note.txt
