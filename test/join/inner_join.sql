SELECT Students.name
FROM Students, Takes
WHERE Takes.sid = Students.id OR Students.id >= 3