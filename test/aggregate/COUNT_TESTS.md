# COUNT Test Suite

This document describes the test cases for COUNT(*) and COUNT(col) aggregate support.

## Test Cases

### 1. Basic Equivalence Tests

**Test**: `count_test1.sql` vs `count_test2.sql`
```sql
-- count_test1.sql
SELECT COUNT(*) FROM Students WHERE age > 18

-- count_test2.sql
SELECT COUNT(*) FROM Students S WHERE S.age > 18
```
**Expected**: EQUIVALENT ✅
**Reason**: Same query, just different table aliasing

---

### 2. Different WHERE Conditions

**Test**: `count_diff1.sql` vs `count_diff2.sql`
```sql
-- count_diff1.sql
SELECT COUNT(*) FROM Students WHERE age > 18

-- count_diff2.sql
SELECT COUNT(*) FROM Students WHERE age > 20
```
**Expected**: NOT EQUIVALENT ✅
**Counterexample**: Student with age=19 matches Q1 but not Q2

---

### 3. COUNT(*) with INNER JOIN

**Test**: `count_join1.sql` vs `count_join2.sql`
```sql
-- count_join1.sql
SELECT COUNT(*) FROM Students S INNER JOIN Takes T ON S.id = T.sid WHERE S.age > 18

-- count_join2.sql
SELECT COUNT(*) FROM Takes T INNER JOIN Students S ON T.sid = S.id WHERE S.age > 18
```
**Expected**: EQUIVALENT ✅
**Reason**: INNER JOIN is commutative (order doesn't matter)

---

### 4. COUNT(*) with LEFT JOIN

**Test**: `count_left_join1.sql` vs `count_left_join2.sql`
```sql
-- Both queries
SELECT COUNT(*) FROM Students S LEFT JOIN Takes T ON S.id = T.sid
```
**Expected**: EQUIVALENT ✅
**Reason**: COUNT(*) includes null-extended rows from LEFT JOIN

---

### 5. Empty Result Sets

**Test**: `count_empty1.sql` vs `count_empty2.sql`
```sql
-- count_empty1.sql
SELECT COUNT(*) FROM Students WHERE age > 1000

-- count_empty2.sql
SELECT COUNT(*) FROM Students WHERE age > 1000
```
**Expected**: EQUIVALENT ✅
**Reason**: Both return 0 (no rows match impossible conditions)

---

### 6. Aliased Aggregates

**Test**: `count2.sql` (from existing tests)
```sql
SELECT COUNT(*) AS cnt FROM Students S
```
**Expected**: Works correctly ✅
**Reason**: Handles aliases on COUNT(*) expressions

---

### 7. Type Mismatch (Sanity Check)

**Test**: `count_test1.sql` vs `count_vs_regular.sql`
```sql
-- count_test1.sql
SELECT COUNT(*) FROM Students WHERE age > 18

-- count_vs_regular.sql
SELECT * FROM Students WHERE age > 18
```
**Expected**: REJECTED by sanity checker ✅
**Reason**: Different output schema (aggregate vs columns)

---

## COUNT(col) Test Cases

### 8. COUNT(*) vs COUNT(nullable_col)

**Test**: `count_col1a.sql` vs `count_col1b.sql`
```sql
-- count_col1a.sql
SELECT COUNT(*) FROM Students

-- count_col1b.sql
SELECT COUNT(age) FROM Students
```
**Expected**: NOT EQUIVALENT ✅
**Reason**: COUNT(*) counts all rows, COUNT(age) only counts rows where age IS NOT NULL
**Counterexample**: Student row with NULL age → COUNT(*) = 1, COUNT(age) = 0

---

### 9. COUNT(col) on NOT NULL Columns

**Test**: `count_col2a.sql` vs `count_col2b.sql`
```sql
-- count_col2a.sql
SELECT COUNT(name) FROM Students

-- count_col2b.sql
SELECT COUNT(id) FROM Students
```
**Expected**: EQUIVALENT ✅
**Reason**: Both name and id are NOT NULL in schema, so they count the same rows

---

### 10. COUNT(col) with NULL-Filtering WHERE

**Test**: `count_col3a.sql` vs `count_col3b.sql`
```sql
-- count_col3a.sql
SELECT COUNT(age) FROM Students WHERE age IS NULL

-- count_col3b.sql
SELECT COUNT(*) FROM Students WHERE 1 = 0
```
**Expected**: EQUIVALENT ✅
**Reason**: Both return 0 (COUNT(age) doesn't count NULL values, so filtering for NULL age yields 0)

---

### 11. COUNT(col) with NOT NULL WHERE Clause

**Test**: `count_col4a.sql` vs `count_col4b.sql`
```sql
-- count_col4a.sql
SELECT COUNT(age) FROM Students WHERE age IS NOT NULL

-- count_col4b.sql
SELECT COUNT(*) FROM Students WHERE age IS NOT NULL
```
**Expected**: EQUIVALENT ✅
**Reason**: When WHERE filters out NULLs, COUNT(age) = COUNT(*) for that column

---

### 12. Identical COUNT(col) Queries

**Test**: `count_col5a.sql` vs `count_col5b.sql`
```sql
-- Both queries
SELECT COUNT(age) FROM Students
```
**Expected**: EQUIVALENT ✅
**Reason**: Identical queries should always be equivalent

---

### 13. COUNT(col) with LEFT JOIN - Null Introduction

**Test**: `count_col_join1a.sql` vs `count_col_join1b.sql`
```sql
-- count_col_join1a.sql
SELECT COUNT(Takes.sid) FROM Students LEFT JOIN Takes ON 1 = 0

-- count_col_join1b.sql
SELECT COUNT(Students.id) FROM Students LEFT JOIN Takes ON 1 = 0
```
**Expected**: NOT EQUIVALENT ✅
**Reason**: Failed LEFT JOIN introduces NULL row for Takes
**Counterexample**:
- Q1: Takes.sid is NULL → COUNT(Takes.sid) = 0
- Q2: Students.id exists → COUNT(Students.id) = 1

---

### 14. COUNT(col) vs COUNT(*) with Nullable Join Column

**Test**: `count_col_join2a.sql` vs `count_col_join2b.sql`
```sql
-- count_col_join2a.sql
SELECT COUNT(Takes.GPA) FROM Students LEFT JOIN Takes ON Students.id = Takes.sid

-- count_col_join2b.sql
SELECT COUNT(*) FROM Students LEFT JOIN Takes ON Students.id = Takes.sid
```
**Expected**: NOT EQUIVALENT ✅
**Reason**: When LEFT JOIN fails to match, Takes.GPA is NULL
**Counterexample**: Student with no matching Takes row
- Q1: COUNT(Takes.GPA) = 0 (NULL value not counted)
- Q2: COUNT(*) = 1 (null-extended row still counted)

---

## How to Run Tests

### COUNT(*) Tests

```bash
# Equivalent queries (should return "unsat")
python main.py test/aggregate/create-table.sql test/aggregate/count_test1.sql test/aggregate/count_test2.sql

# Non-equivalent queries (should return "sat" with counterexample)
python main.py test/aggregate/create-table.sql test/aggregate/count_diff1.sql test/aggregate/count_diff2.sql

# JOIN tests
python main.py test/aggregate/create-table.sql test/aggregate/count_join1.sql test/aggregate/count_join2.sql
python main.py test/aggregate/create-table.sql test/aggregate/count_left_join1.sql test/aggregate/count_left_join2.sql

# Empty result set
python main.py test/aggregate/create-table.sql test/aggregate/count_empty1.sql test/aggregate/count_empty2.sql

# Aliased aggregate
python main.py test/aggregate/create-table.sql test/aggregate/count2.sql test/aggregate/count2.sql
```

### COUNT(col) Tests

```bash
# COUNT(*) vs COUNT(nullable_col) - non-equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col1a.sql \
  test/aggregate/count_col1b.sql

# COUNT on NOT NULL columns - equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col2a.sql \
  test/aggregate/count_col2b.sql

# COUNT(col) with NULL filtering - equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col3a.sql \
  test/aggregate/count_col3b.sql

# COUNT(col) with NOT NULL WHERE - equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col4a.sql \
  test/aggregate/count_col4b.sql

# Identical COUNT(col) queries - equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col5a.sql \
  test/aggregate/count_col5b.sql

# COUNT(col) with LEFT JOIN null introduction - non-equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col_join1a.sql \
  test/aggregate/count_col_join1b.sql

# COUNT(col) vs COUNT(*) with nullable join column - non-equivalent
python main.py test/aggregate/create-table.sql \
  test/aggregate/count_col_join2a.sql \
  test/aggregate/count_col_join2b.sql
```

## All Tests Pass ✅

All test cases execute successfully and produce the expected results.
