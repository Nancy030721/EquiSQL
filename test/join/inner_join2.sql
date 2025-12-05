SELECT S.name
FROM Students S
JOIN Takes ON Takes.sid = S.id
OR id >= 3