SELECT Students.name
FROM Students
LEFT OUTER JOIN Takes ON Students.id = Takes.sid 
WHERE Takes.GPA >= 3.0