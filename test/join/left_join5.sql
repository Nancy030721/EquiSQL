SELECT S.id
FROM Students AS S
LEFT JOIN Takes AS T ON S.id = T.sid;
