from dal.user_dao import UserDAO

uid="admin"
pwd="123"
us=UserDAO.login(uid,pwd)
if us is None:
    print("Login failed")
else:
    print("Login success")
    print("welcome",us.username)
