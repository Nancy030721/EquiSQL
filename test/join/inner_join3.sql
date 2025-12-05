SELECT Students.id, Students.name, Students.age, Takes.cid, Takes.GPA
FROM Students, Takes
WHERE Takes.sid = Students.id
-- SELECT Students.id, Students.name, Students.age, Takes.cid, Takes.GPA
-- FROM Students
-- LEFT JOIN Takes ON Takes.sid = Students.id
-- OR Students.id >= 3 OR Students.name LIKE 'Nancy%';