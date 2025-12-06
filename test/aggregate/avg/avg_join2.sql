-- AVG with JOIN (equivalent form)
SELECT AVG(S.age) FROM Students S INNER JOIN Takes T ON S.id = T.sid

