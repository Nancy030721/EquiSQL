SELECT *
FROM Students
RIGHT OUTER JOIN Takes ON Takes.sid = Students.id LIMIT 1;