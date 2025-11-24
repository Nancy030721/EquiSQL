SELECT S.id
FROM Students AS S
RIGHT JOIN Takes AS T ON S.id = T.sid;
