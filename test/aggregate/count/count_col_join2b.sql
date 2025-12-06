-- COUNT(*) in LEFT JOIN
SELECT COUNT(*) FROM Students LEFT JOIN Takes ON Students.id = Takes.sid
