-- SELECT *
-- FROM Students S
-- LEFT JOIN Takes T
-- ON S.id = T.sid
-- WHERE S.id is null

SELECT *
FROM Students S
LEFT JOIN Takes T
ON S.id = T.sid or S.id is null