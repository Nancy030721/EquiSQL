SELECT distinct S.id, T.sid
FROM Students S 
LEFT JOIN Takes T 
ON S.id = T.sid 