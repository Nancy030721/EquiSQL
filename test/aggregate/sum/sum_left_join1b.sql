-- SUM on left table column when join fails (should be id value)
SELECT SUM(Students.id) FROM Students LEFT JOIN Takes ON 1 = 0

