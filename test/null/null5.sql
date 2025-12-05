SELECT *
FROM Students S
LEFT JOIN Takes T 
ON S.id = T.sid 
WHERE T.sid IS NULL
-- after left join, we have (And(S present, T present, S.id=T.sid), S, T) and (And(not match, S pressent), S, NULL)
-- after where, we will get (not match, S, NULL), 
-- because nothing in (And(S present, T present, S.id=T.sid), S, T) will survive


-- null 6:
-- SELECT *
-- FROM Students S
-- FULL JOIN Takes T 
-- ON S.id = T.sid
-- WHERE S.id IS NOT NULL AND T.sid IS NULL

-- after full join, we have (And(S present, T present, S.id=T.sid), S, T), (And(not match, S pressent), S, NULL), (And(not match, T present), NULL, T)
-- after where, similary nothing in the first group (matched group) survive
-- the second group survive
-- the third does not

-- counterexample we get:
-- S.id is NULL, Takes.sid is NOT NULL 
-- q1_left_null is false (which means no (NULL, S) is passed to where)
-- but it be the case where we have (id, name, age, sid, cid, GPA) = (NULL, "ABC", 20, 123, 414)
