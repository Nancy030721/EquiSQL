-- SUM with INNER JOIN
SELECT SUM(S.age) FROM Students S INNER JOIN Takes T ON S.id = T.sid WHERE S.age > 18

