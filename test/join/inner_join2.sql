SELECT Students.name
FROM Students
JOIN Takes ON Takes.sid = Students.id
OR Students.id >= 3