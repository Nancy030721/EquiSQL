SELECT S.id, S.name, S.age, T.cid, T.GPA
FROM Takes AS T
RIGHT JOIN Students AS S
    ON T.sid = S.id
WHERE T.sid IS NOT NULL;

