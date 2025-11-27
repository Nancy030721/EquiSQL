SELECT distinct Students.id
FROM Students S 
LEFT JOIN Takes T 
ON S.id = T.sid 