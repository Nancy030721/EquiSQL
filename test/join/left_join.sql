SELECT Students.name
FROM Students
LEFT JOIN Takes ON Students.id = Takes.sid 
WHERE Students.id >= 3