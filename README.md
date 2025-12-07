# EquiSQL

EquiSQL is a lightweight SQL query equivalence checker that uses SMT solving to reason about whether two SQL queries are semantically equivalent.  It parses SQL queries, converts them into logical formulas, and invokes the Z3 solver to search for counterexamples—cases where the queries return different results.

## Current Features

### Core SQL Operations
- **SELECT, FROM, WHERE clauses**: Full support for basic query structure
- **Multiple tables**: Can query and join multiple tables
- **Table aliasing**: Allows table aliases in queries (e.g., `FROM Students S`)

### JOIN Support
- **INNER JOIN**: Explicit and implicit inner joins with ON conditions
- **LEFT JOIN**: Left outer join support
- **RIGHT JOIN**: Right outer join support
- **FULL JOIN**: Full outer join support
- **Cartesian Product**: Implicit cross joins (comma-separated tables)

### Data Types
- **INT/INTEGER**: Integer data type
- **REAL**: Floating-point numbers
- **TEXT/STRING**: String data type

### Logical & Comparison Operations
- **Comparison operators**: `=`, `<>`, `<`, `>`, `<=`, `>=`
- **Logical operators**: `AND`, `OR`, `NOT`
- **NULL handling**: `IS NULL`, `IS NOT NULL` conditions
- **NOT NULL constraints**: Recognizes attributes declared as NOT NULL in table definitions

### Arithmetic Operations
- **Addition, subtraction, multiplication**: Supports `+`, `-`, `*` operators in expressions

### Aggregate Functions
- **COUNT(*)**: Count all rows
- **COUNT(col)**: Count non-null values in a column
- **SUM(col)**: Sum values in a column (ignoring nulls)
- **AVG(col)**: Average values in a column (ignoring nulls)

### SMT Solver Integration
- **Z3 solver**: Primary solver support
- **CVC5 solver**: Alternative solver support with `-cvc5` flag
- **Counterexample generation**: Reports specific database instances where queries differ

## Limitations
- No support for DISTINCT, GROUP BY, HAVING, ORDER BY, LIMIT, OFFSET
- No support for subqueries or nested queries
- Aggregate functions currently work with single-row results (no GROUP BY)
- Limited to aggregate functions on direct column references (not expressions)

## Example usage
### Run from the command line using Z3
```bash
python main.py test/create-table.sql test/query1.sql test/query2.sql
```
### Run tests using Z3
```bash
python run_test.py
```
### Run from the command line using CVC5
```bash
python main.py test/create-table.sql test/query1.sql test/query2.sql -cvc5
```
### Run tests using CVC5
```bash
python run_test.py -cvc5
```

For more details on ongoing process, check note.txt
