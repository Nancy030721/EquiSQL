-- SUM with INNER JOIN (reversed order)
SELECT SUM(S.age) FROM Takes T INNER JOIN Students S ON T.sid = S.id WHERE S.age > 18

