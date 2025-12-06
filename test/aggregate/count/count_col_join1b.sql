-- COUNT on left table column when join fails (should be 1)
SELECT COUNT(Students.id) FROM Students LEFT JOIN Takes ON 1 = 0
