<<<<<<< HEAD
# ML2026_Final

## 1. Cài đặt database
Thư mục `databases/` có 1 file dữ liệu (khoảng 100.000 dòng). **Chọn để nạp vào MySQL Workbench của em:
- `databaseFinal.sql`

## 2. Các thư viện cần cài
![img.png](img.png)
## 3. Lấy code từ GitHub (Pull / Clone)
**Lần đầu:**
1. Cài Git từ [git-scm.com](https://git-scm.com). Kiểm tra bằng cách mở cmd và gõ:
```
   git --version
```
2. Mở cmd tại nơi muốn lưu project và chạy:
```
   git clone https://github.com/Quyss2/ML2026_Final.git
   cd ML2026_Final
```

**Những lần sau** (đã clone rồi, chỉ cần lấy bản mới):

```
git pull
```

Không cần clone lại từ đầu.

## 4. Đẩy code lên GitHub (Push)

Mở cmd trong thư mục project và chạy lần lượt:

```
git pull
git add .
git status
git commit -m "<tên version> - <tên người đăng>"
git push origin main
```

Ví dụ: `git commit -m "Them man hinh bieu do - Quy"`

**Lưu ý:**
- Luôn chạy `git pull` trước khi push để tránh xung đột với code của người khác.
- Sau khi `git clone`, repo đã tự nối với GitHub nên **không cần** chạy `git remote add origin`. Lệnh này chỉ dùng cho người tạo repo lần đầu.
- Lần đầu commit, nếu Git báo thiếu tên/email, chạy:
```
  git config --global user.name "Ten Cua Ban"
  git config --global user.email "email@cuaban.com"
```
=======
Cách tạo nhập database:
có 2 file database (databaseFinal.sql và FinalDatabase.csv)  (100.000 dòng) trong file database chọn 1 trong 2 up lên mysql workbench của mình
--------------------
Cách pull và push dữ liệu lên github 
Pull dữ liêu: 
    B1: Cài Git từ git-scm.com. ( kiểm tra github: mở cmd và nhập git --version)
    B2: Tạo folder "MLFinal_2026" và nhập vào cmd:  **git clone https://github.com/Quyss2/ML2026_Final.git**
(trường hợp đã pull lần 1 và anh có push bản mới thì nhập vào cmd: **git pull** không cần pull lại từ đầu
--------------------
Push dữ liệu: 
    B1: vào cmd 
    B2: Nhập lần lượt vào cmd: 
git add . 
git status
git commit -m "<đặt tên cho version + tên của người đăng>"
git remote add origin https://github.com/Quyss2/ML2026_Final.git
git push -u origin main
Các thư viện cần cài:  ![img.png](img.png)
>>>>>>> 092146d5543e6f5c687c5bbdb6a9736ee437938f
