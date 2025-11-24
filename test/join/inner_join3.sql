SELECT Students.id, Students.name, Students.age, Takes.cid, Takes.GPA
FROM Students, Takes
WHERE Takes.sid = Students.id