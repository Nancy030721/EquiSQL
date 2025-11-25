SELECT S.id, S.name, S.age, T.cid, T.GPA
FROM Students AS S
FULL JOIN Takes AS T
    ON S.id = T.sid
WHERE T.sid IS NOT NULL AND S.id IS NOT NULL

-- SELECT *
-- FROM Students S
-- INNER JOIN Takes T
-- ON S.id = T.sid