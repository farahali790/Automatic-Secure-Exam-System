p = "templates/student.html"
s = open(p, encoding="utf-8").read()
n = s
n = n.replace("localStorage.getItem('student_token')", "localStorage.getItem('se_token')")
n = n.replace("localStorage.setItem('student_token', token)", "localStorage.setItem('se_token', token)")
if s != n:
    open(p, "w", encoding="utf-8").write(n)
    print("patched: student.html now stores token as 'se_token'")
else:
    print("no change — patterns not found, check file manually")