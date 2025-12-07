-- SUM on right table column when join fails (should be 0)
SELECT SUM(Takes.sid) as sum FROM Students LEFT JOIN Takes ON 1 = 0

