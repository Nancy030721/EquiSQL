-- SUM ignores NULL values (nullable age column)
SELECT SUM(age) FROM Students WHERE age IS NOT NULL

