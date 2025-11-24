SELECT S.id, S.name, S.age, T.sid, T.cid, T.GPA
FROM Takes as T
LEFT JOIN Students S ON S.id = T.sid LIMIT 1;