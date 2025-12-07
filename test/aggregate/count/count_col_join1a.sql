-- COUNT on right table column when join fails (should be 0)
SELECT COUNT(Takes.sid) as cnt FROM Students LEFT JOIN Takes ON 1 = 0
