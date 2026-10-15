from dal.customer_dao import CustomerDAO

df = CustomerDAO().getAllCustomers()
print(df)
df = CustomerDAO.searchByNameCosine("Nguyễn Văn Toàn", 5)
print(df)