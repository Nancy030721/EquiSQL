SELECT Students.name
FROM Students
LEFT OUTER JOIN Takes ON Students.id = Takes.sid 
AND Students.id >= 3