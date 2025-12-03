SELECT *
FROM Students, Takes
WHERE Students.id = Takes.sid OR Students.id != Takes.sid 