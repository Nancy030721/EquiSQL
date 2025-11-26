SELECT Students.id, Students.name, Students.age, Takes.cid, Takes.GPA
FROM Students, Takes
WHERE Takes.sid = Students.id

-- SELECT *
-- FROM Students S
-- LEFT JOIN Takes T
-- ON S.id = T.sid
-- WHERE T.sid is not null