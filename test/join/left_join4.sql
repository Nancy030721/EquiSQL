SELECT S.id, S.name, S.age, T.cid, T.GPA
FROM Students AS S
LEFT JOIN Takes AS T
    ON S.id = T.sid
WHERE T.sid IS NOT NULL;
