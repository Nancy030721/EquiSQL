# EquiSQL

EquiSQL is a lightweight SQL query equivalence checker that uses SMT solving to reason about whether two SQL queries are semantically equivalent.  It parses SQL queries, converts them into logical formulas, and invokes the Z3 solver to search for counterexamples—cases where the queries return different results.

## Current Features
- Supports a small subset of SQL (`SELECT`, `FROM`, `WHERE`), single table, no table aliasing
- Supports simple conjunction, disconjuction, and arithematic logic
- Translates queries into logical constraints for Z3
- Reports counterexamples when queries differ

## Example usage
command line: 
python main.py create-table.sql query1.sql query2.sql

## What we will explore next
- Extend support to queries involving multiple tables  
- Handle table aliases in SQL statements
- Add support for other arithematic operations, such as +, -, *
- Add support for various join types (`INNER`, `LEFT OUTER`, `RIGHT OUTER`, `FULL JOIN`)  
- Integrate additional SMT solvers such as CVC5
