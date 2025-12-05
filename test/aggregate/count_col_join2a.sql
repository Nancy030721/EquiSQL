-- COUNT(nullable_col) from right table in LEFT JOIN
SELECT COUNT(Takes.GPA) FROM Students LEFT JOIN Takes ON Students.id = Takes.sid
