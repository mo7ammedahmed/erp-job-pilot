"""Drive the apply engine against local mock ATS forms to verify filling, CAPTCHA stops, and submit.

Not part of the pytest suite: it needs a live Chromium and a local HTTP server.
Run:  .\\.venv\\Scripts\\python.exe -X utf8 scripts\\test_apply_engine.py
"""
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["JOBPILOT_APPLY_EXTRA_HOSTS"] = "127.0.0.1"

import apply as A  # noqa: E402

FORM = """<!doctype html><html><head><title>Application for Backend Engineer</title></head>
<body>
<form action="/submitted" method="post">
  <label for="first_name">First Name</label><input id="first_name" name="first_name" required>
  <label for="last_name">Last Name</label><input id="last_name" name="last_name" required>
  <label for="email_address">Email Address</label><input id="email_address" name="email" type="email" required>
  <label for="phone_number">Phone Number</label><input id="phone_number" name="phone" type="tel">
  <label for="li">LinkedIn</label><input id="li" name="linkedin_url">
  <label for="loc">Current Location</label><input id="loc" name="location">
  <label for="cv">Resume</label><input id="cv" type="file" accept=".pdf,.doc,.docx" required>
  <label for="cl">Why are you interested in this role?</label>
  <textarea id="cl" name="cover_letter" required></textarea>
  <button type="submit">Submit Application</button>
</form></body></html>"""

CAPTCHA_FORM = """<!doctype html><html><head><title>Just a moment...</title></head>
<body><iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>
<p>Verify you are human</p></body></html>"""

REQUIRED_MISSING = """<!doctype html><html><head><title>Apply</title></head><body>
<form><label for="a">Email</label><input id="a" name="email" type="email" required>
<label for="b">Work authorization number</label><input id="b" name="auth_number" required>
<button type="submit">Submit</button></form></body></html>"""

DONE = """<!doctype html><html><head><title>Thanks</title></head>
<body><h1>Thank you for applying!</h1><p>We have received your application.</p></body></html>"""

ROUTES = {"/job": FORM, "/captcha": CAPTCHA_FORM, "/missing": REQUIRED_MISSING, "/submitted": DONE}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ROUTES.get(self.path, "").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *a):
        pass


def main():
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    base = f"http://127.0.0.1:{port}"

    profile = {"first_name": "Sara", "last_name": "Al Ahmed", "full_name": "Sara Al Ahmed",
               "email": "sara@example.com", "phone": "+966500000000",
               "linkedin": "https://linkedin.com/in/sara", "website": "https://sara.dev",
               "location": "Riyadh, Saudi Arabia", "cover_letter": "I am excited about this role."}
    cv = (b"%PDF-1.4 fake cv bytes for testing", {"filename": "Sara_Al_Ahmed_CV.pdf"})

    fails = []

    def check(label, cond, detail=""):
        print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))
        if not cond:
            fails.append(label)

    r = A.run_apply(f"{base}/job", profile, cv=cv, submit=False)
    check("fills every field in preview mode", set(r["filled"]) >= {
        "first_name", "last_name", "email", "phone", "linkedin", "location", "cover_letter", "cv"},
          f"status={r['status']} filled={r['filled']} blockers={r['blockers']}")

    r = A.run_apply(f"{base}/job", profile, cv=cv, submit=True)
    check("submits a complete form", r["status"] == "submitted" and r["submitted"],
          f"status={r['status']} msg={r['message']} url={r['final_url']}")
    check("captures screenshot evidence", bool(r["screenshot"]))
    if r["screenshot"]:
        Path(r["screenshot"]).unlink(missing_ok=True)

    r = A.run_apply(f"{base}/captcha", profile, cv=cv, submit=True)
    check("stops on CAPTCHA and never submits", r["status"] == "needs_human" and not r["submitted"],
          f"status={r['status']} blockers={r['blockers']}")
    if r["screenshot"]:
        Path(r["screenshot"]).unlink(missing_ok=True)

    r = A.run_apply(f"{base}/missing", profile, cv=None, submit=True)
    check("stops when a required field is unknown", r["status"] == "needs_human" and not r["submitted"],
          f"status={r['status']} blockers={r['blockers']}")
    if r["screenshot"]:
        Path(r["screenshot"]).unlink(missing_ok=True)

    r = A.run_apply("https://evil.example.com/jobs/1", profile, cv=cv, submit=True)
    check("refuses an unmodelled host", r["status"] == "unsupported", f"status={r['status']}")

    r = A.run_apply(f"{base}/job", {"email": "only@example.com"}, cv=None, submit=True)
    check("missing profile fields reported, not guessed", r["status"] in ("needs_human", "unknown"),
          f"status={r['status']} blockers={r['blockers']}")
    if r["screenshot"]:
        Path(r["screenshot"]).unlink(missing_ok=True)

    srv.shutdown()
    print("\nRESULT:", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
