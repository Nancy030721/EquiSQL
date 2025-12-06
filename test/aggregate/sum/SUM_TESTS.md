# SUM Test Suite

This document describes the test cases for SUM(col) aggregate support.

## Test Cases

### 1. Basic Equivalence Tests - Integer Column

**Test**: `sum_col1a.sql` vs `sum_col1b.sql`
```sql
-- sum_col1a.sql
SELECT SUM(age) FROM Students

-- sum_col1b.sql
SELECT SUM(S.age) FROM Students S
```
**Expected**: EQUIVALENT ✅
**Reason**: Same query, just different table aliasing. Both sum the age column.

---

### 2. Basic Equivalence Tests - NOT NULL Column

**Test**: `sum_col2a.sql` vs `sum_col2b.sql`
```sql
-- sum_col2a.sql
SELECT SUM(id) FROM Students

-- sum_col2b.sql
SELECT SUM(Students.id) FROM Students
```
**Expected**: EQUIVALENT ✅
**Reason**: Same query with explicit table qualification. id is a NOT NULL column.

---

### 3. Basic Equivalence Tests - Real Number Column

**Test**: `sum_real1a.sql` vs `sum_real1b.sql`
```sql
-- sum_real1a.sql
SELECT SUM(GPA) FROM Takes

-- sum_real1b.sql
SELECT SUM(T.GPA) FROM Takes T
```
**Expected**: EQUIVALENT ✅
**Reason**: Same query on a REAL column (GPA), with/without alias.

---

### 4. SUM with WHERE Clause

**Test**: `sum_where1a.sql` vs `sum_where1b.sql`
```sql
-- sum_where1a.sql
SELECT SUM(age) FROM Students WHERE age > 18

-- sum_where1b.sql
SELECT SUM(S.age) FROM Students S WHERE S.age > 18
```
**Expected**: EQUIVALENT ✅
**Reason**: Same query with WHERE filtering, different aliasing styles.

---

### 5. Different WHERE Conditions

**Test**: `sum_diff1.sql` vs `sum_diff2.sql`
```sql
-- sum_diff1.sql
SELECT SUM(age) FROM Students WHERE age > 18

-- sum_diff2.sql
SELECT SUM(age) FROM Students WHERE age > 20
```
**Expected**: NOT EQUIVALENT ✅
**Counterexample**: Student with age=19 contributes to Q1's sum but not Q2's.

---

### 6. SUM with INNER JOIN

**Test**: `sum_join1.sql` vs `sum_join2.sql`
```sql
-- sum_join1.sql
SELECT SUM(S.age) FROM Students S INNER JOIN Takes T ON S.id = T.sid WHERE S.age > 18

-- sum_join2.sql
SELECT SUM(S.age) FROM Takes T INNER JOIN Students S ON T.sid = S.id WHERE S.age > 18
```
**Expected**: EQUIVALENT ✅
**Reason**: INNER JOIN is commutative - order of tables doesn't affect the result.

---

### 7. SUM with LEFT JOIN - Right Table Column

**Test**: `sum_left_join1a.sql` vs `sum_left_join1b.sql`
```sql
-- sum_left_join1a.sql
SELECT SUM(Takes.sid) FROM Students LEFT JOIN Takes ON 1 = 0

-- sum_left_join1b.sql
SELECT SUM(Students.id) FROM Students LEFT JOIN Takes ON 1 = 0
```
**Expected**: NOT EQUIVALENT ✅
**Counterexample**:
- Q1: join always fails (1=0), Takes.sid is NULL → SUM = 0
- Q2: join always fails but Students row exists → SUM = Students.id

---

### 8. SUM with NULL Handling

**Test**: `sum_null1.sql` vs `sum_null2.sql`
```sql
-- sum_null1.sql
SELECT SUM(age) FROM Students WHERE age IS NOT NULL

-- sum_null2.sql
SELECT SUM(age) FROM Students
```
**Expected**: EQUIVALENT ✅
**Reason**: SUM automatically ignores NULL values. Explicitly filtering NULLs doesn't change the result.

---

### 9. SUM vs COUNT - Different Aggregates

**Test**: `sum_vs_count.sql` vs `count_same_table.sql`
```sql
-- sum_vs_count.sql
SELECT SUM(id) FROM Students

-- count_same_table.sql
SELECT COUNT(id) FROM Students
```
**Expected**: NOT EQUIVALENT ✅
**Counterexample**:
- SUM(id) adds up all id values (e.g., 1+2+3 = 6)
- COUNT(id) counts rows (e.g., 3 rows = 3)

---

## How to Run Tests

### Test Equivalence (Expected: EQUIVALENT)
```bash
python main.py test/create-table.sql test/aggregate/sum/sum_col1a.sql test/aggregate/sum/sum_col1b.sql
python main.py test/create-table.sql test/aggregate/sum/sum_col2a.sql test/aggregate/sum/sum_col2b.sql
python main.py test/create-table.sql test/aggregate/sum/sum_real1a.sql test/aggregate/sum/sum_real1b.sql
python main.py test/create-table.sql test/aggregate/sum/sum_where1a.sql test/aggregate/sum/sum_where1b.sql
python main.py test/create-table.sql test/aggregate/sum/sum_join1.sql test/aggregate/sum/sum_join2.sql
python main.py test/create-table.sql test/aggregate/sum/sum_null1.sql test/aggregate/sum/sum_null2.sql
```

### Test Non-Equivalence (Expected: NOT EQUIVALENT with counterexample)
```bash
python main.py test/create-table.sql test/aggregate/sum/sum_diff1.sql test/aggregate/sum/sum_diff2.sql
python main.py test/create-table.sql test/aggregate/sum/sum_left_join1a.sql test/aggregate/sum/sum_left_join1b.sql
python main.py test/create-table.sql test/aggregate/sum/sum_vs_count.sql test/aggregate/sum/count_same_table.sql
```

## SUM Semantics

### NULL Handling
- SUM ignores NULL values in the column
- If all values are NULL or no rows match, SUM returns 0

### Type Constraints
- SUM works on numeric columns: INT and REAL
- Cannot use SUM on STRING columns

### One-Row Semantics (Current Implementation)
In your one-row-per-table model:
- SUM(col) = col_value if row exists AND col is NOT NULL
- SUM(col) = 0 if no row exists OR col is NULL

### JOIN Behavior
- INNER JOIN: SUM only includes matched rows
- LEFT JOIN: SUM includes left table's column even when right table is NULL
- For NULL-padded rows (e.g., right table in LEFT JOIN), those columns contribute 0 to the sum

---

## Coverage Matrix

| Test Category | Test Files | Expected Result |
|--------------|------------|-----------------|
| Basic (INT) | sum_col1a vs sum_col1b | ✅ EQUIVALENT |
| NOT NULL (INT) | sum_col2a vs sum_col2b | ✅ EQUIVALENT |
| REAL numbers | sum_real1a vs sum_real1b | ✅ EQUIVALENT |
| WHERE clause | sum_where1a vs sum_where1b | ✅ EQUIVALENT |
| Different WHERE | sum_diff1 vs sum_diff2 | ❌ NOT EQUIVALENT |
| INNER JOIN | sum_join1 vs sum_join2 | ✅ EQUIVALENT |
| LEFT JOIN | sum_left_join1a vs sum_left_join1b | ❌ NOT EQUIVALENT |
| NULL handling | sum_null1 vs sum_null2 | ✅ EQUIVALENT |
| SUM vs COUNT | sum_vs_count vs count_same_table | ❌ NOT EQUIVALENT |

---

## Implementation Notes

The SUM encoding follows this logic:
```python
# For SUM(col):
sum_val = Int(f"q{idx}_sum_col_result")
s.add(sum_val == If(And(row_exists, Not(col_is_null)), col_val, 0))
```

This encodes SQL's behavior:
1. If row exists AND column is NOT NULL → use the column value
2. Otherwise (no row or NULL column) → use 0 as the neutral element

