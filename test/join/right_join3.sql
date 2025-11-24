SELECT S.id, S.name, S.age, T.cid, T.GPA
FROM Students AS S
RIGHT JOIN Takes AS T
    ON S.id = T.sid
WHERE S.id IS NOT NULL;
