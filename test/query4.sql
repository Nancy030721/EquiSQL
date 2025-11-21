SELECT Customer.cname 
FROM Customer, Orders 
WHERE Customer.cid = Orders.cid and Orders.price - 41 = 41 * 2;