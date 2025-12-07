-- COUNT on left table column when join fails (should be 1)
SELECT COUNT(Students.id) as cnt FROM Students LEFT JOIN Takes ON 1 = 0
