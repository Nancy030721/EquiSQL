assertions:[
   Students_q1_id == Students_q2_id
   Students_q1_name == Students_q2_name
   Students_q1_age == Students_q2_age
   Takes_q1_sid == Takes_q2_sid
   Takes_q1_cid == Takes_q2_cid
   Takes_q1_GPA == Takes_q2_GPA

   q1_cond_where == NullInt(Students__id)

   q1_result ==
And(Or(Not(And(Students_q1_id == Takes_q1_sid,
               Not(NullInt(Students__id)),
               Not(NullInt(Takes__sid)))),
       JOIN(Students_row, Takes_row)),
    Or(JOIN(Students_row, -1),
       And(Students_q1_id == Takes_q1_sid,
           Not(NullInt(Students__id)),
           Not(NullInt(Takes__sid)))),
    q1_cond_where,
    Not(NullString(Students__name)))


   q2_result ==
And(Not(JOIN(Students_row, Takes_row)),
    Not(NullInt(Students__id)),
    Not(NullString(Students__name)))
    
   Not(q1_result == q2_result)
]