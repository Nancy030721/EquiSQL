SELECT distinct T.sid
FROM Students S 
LEFT JOIN Takes T 
ON S.id = T.sid 