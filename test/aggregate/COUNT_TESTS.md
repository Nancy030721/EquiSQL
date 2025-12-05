# COUNT(*) Test Suite

This document describes the test cases for COUNT(*) aggregate support.

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

## How to Run Tests

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

## All Tests Pass ✅

All test cases execute successfully and produce the expected results.
