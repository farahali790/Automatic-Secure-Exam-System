p = "app.py"
s = open(p, encoding="utf-8").read()
diag = '''
# ----- TEMP JWT DIAGNOSTIC (remove after debugging) -----
@app.before_request
def _log_auth():
    from flask import request
    if request.path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        shown = (auth[:30] + "...") if auth else "MISSING"
        print(f"[AUTH-DEBUG] {request.method:5s} {request.path:30s} Auth: {shown}")
# --------------------------------------------------------

'''
if "[AUTH-DEBUG]" in s:
    print("Already added")
else:
    i = s.find("@app.route(")
    if i > 0:
        s = s[:i] + diag + s[i:]
        open(p, "w", encoding="utf-8").write(s)
        print("Added JWT debug — restart Flask")
    else:
        print("Could not find anchor — manual addition needed")