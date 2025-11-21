SELECT S.name
FROM Students as S
LEFT JOIN Takes ON S.id = Takes.sid