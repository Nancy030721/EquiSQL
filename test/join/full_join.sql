SELECT Students.name
FROM Students
FULL OUTER JOIN Takes ON Students.id = Takes.sid 
WHERE Takes.GPA >= 3