SELECT Students.name
FROM Students
RIGHT OUTER JOIN Takes ON Takes.sid = Students.id 
WHERE Takes.GPA >= 3.0