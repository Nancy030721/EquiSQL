SELECT Customer.cname 
FROM Customer
JOIN Orders ON Customer.cid = Orders.cid 
WHERE Orders.price - 3.0 = 120;