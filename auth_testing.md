# Auth testing playbook (JobPilot)

1. JWT email/password: `curl -c c.txt -X POST $URL/api/auth/login -H 'Content-Type: application/json' -d '{"email":"demo@jobpilot.app","password":"Demo@12345"}'` then `curl -b c.txt $URL/api/auth/me`.
   - bcrypt hashes start with `$2b$`; unique index on users.email; 5 failed logins => 15 min lockout (login_attempts).
2. Emergent Google auth: create a session manually in mongo for browser tests:
```
mongosh test_database --eval "var u=db.users.findOne({email:'demo@jobpilot.app'}); db.user_sessions.insertOne({user_id:u.user_id, session_token:'test_session_1', expires_at:new Date(Date.now()+7*864e5).toISOString(), created_at:new Date().toISOString()})"
```
   then `curl -H 'Authorization: Bearer test_session_1' $URL/api/auth/me` or set cookie `session_token=test_session_1` (secure, SameSite=None).
3. Frontend: `/login` -> dashboard `/app`; unauthenticated `/app` redirects to `/login`; new users go to `/onboarding`.
