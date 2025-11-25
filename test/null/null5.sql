
SELECT *
FROM Students S
LEFT JOIN Takes T 
ON S.id = T.sid 
WHERE T.sid IS NULL