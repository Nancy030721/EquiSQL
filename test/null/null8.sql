
-- SELECT *
-- FROM Students S
-- INNER JOIN Takes T
-- ON 1>2


SELECT *
FROM Students S, Takes T 
WHERE S.id = T.sid or S.id is null