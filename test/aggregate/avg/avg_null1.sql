-- AVG with nullable columns - filtering out NULLs explicitly
SELECT AVG(gpa) FROM Students WHERE gpa IS NOT NULL

