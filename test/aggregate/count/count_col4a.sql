-- COUNT(age) with WHERE filtering out nulls
SELECT COUNT(age) FROM Students WHERE age IS NOT NULL
