# AVG() Aggregate Function Tests

This directory contains tests for the AVG() aggregate function implementation.

## Test Cases

### Basic AVG Tests

1. **avg_col1a.sql** / **avg_col1b.sql** - EQUIVALENT
   - Basic AVG on integer column (age)
   - Tests equivalence between `AVG(age)` and `AVG(S.age)` with table alias
   - Status: ✅ PASS

### AVG with WHERE Clauses

2. **avg_where1a.sql** / **avg_where1b.sql** - EQUIVALENT
   - AVG with WHERE clause filtering
   - Tests equivalence between queries with and without table alias
   - WHERE age > 20
   - Status: ✅ PASS

3. **avg_diff1.sql** / **avg_diff2.sql** - COUNTEREXAMPLE
   - AVG with different WHERE conditions should NOT be equivalent
   - Q1: WHERE age > 20 vs Q2: WHERE age > 25
   - Status: ✅ PASS (correctly finds counterexample)

### AVG with JOINs

4. **avg_join1.sql** / **avg_join2.sql** - EQUIVALENT
   - AVG with INNER JOIN
   - Tests equivalence between JOIN and INNER JOIN syntax
   - Status: ✅ PASS

### AVG with NULL Handling

5. **avg_null1.sql** / **avg_null2.sql** - Tests AVG NULL semantics
   - AVG naturally ignores NULL values
   - Note: These may not be directly comparable due to WHERE clause differences

## Implementation Details

### Encoding

AVG(col) is encoded as a tuple (numerator, denominator):
- numerator = SUM(col) over non-null values
- denominator = COUNT(col) over non-null values

This allows the solver to reason about AVG equivalence by comparing:
- If numerator1 ≠ numerator2 OR denominator1 ≠ denominator2 → queries are NOT equivalent

### NULL Semantics

AVG(col) follows SQL semantics:
- NULL values are ignored in both the sum and count
- AVG of an empty set (or all NULLs) returns 0/0 representation
- Only non-null values contribute to the average

### Limitations

Current implementation supports:
- ✅ AVG(column_name)
- ✅ AVG with table aliases
- ✅ AVG with WHERE clauses
- ✅ AVG with JOINs (INNER, LEFT, RIGHT, FULL)

Not yet supported:
- ❌ AVG(expression) - e.g., AVG(age + 10)
- ❌ AVG(*) - not valid SQL syntax anyway
- ❌ GROUP BY with AVG - grouped aggregates not supported

## Running Tests

Run individual tests:
```bash
python main.py test/create-table.sql test/aggregate/avg/avg_col1a.sql test/aggregate/avg/avg_col1b.sql -z3
```

Expected Results:
- avg_col1a vs avg_col1b: EQUIVALENT
- avg_where1a vs avg_where1b: EQUIVALENT
- avg_join1 vs avg_join2: EQUIVALENT
- avg_diff1 vs avg_diff2: COUNTEREXAMPLE (not equivalent)

## Related Files

- `z3_encoder.py`: Contains `is_avg_col()`, `extract_aggregate_column()`, AVG encoding logic
- `sanity_checker.py`: Handles AVG in column extraction and supported functions list
- `run_test.py`: Can be extended to include AVG tests in the test suite

