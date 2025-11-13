SELECT Students.name
FROM Students
FULL OUTER JOIN Takes ON Takes.sid = Students.id
WHERE Takes.GPA >= 3