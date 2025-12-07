-- SUM on left table column when join fails (should be id value)
SELECT SUM(Students.id) as sum FROM Students LEFT JOIN Takes ON 1 = 0

