SELECT Students.name
FROM Students, Takes
WHERE Students.id = Takes.sid 
AND Students.id >= 3