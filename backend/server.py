import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core import db, client, iso, hash_password, verify_password, uid, DEFAULT_PLANS, init_storage, logger
from sources import DEFAULT_SOURCES, run_all_sources
from r_auth import router as auth_router, new_user_doc, create_user
from r_cv import router as cv_router
from r_jobs import router as jobs_router
from r_apps import router as apps_router, process_reminders, ghost_check
from r_integrations import router as integ_router, _scan_gmail_inbox
from r_admin import router as admin_router
from r_phase2 import router as phase2_router
from r_coach import router as coach_router
from r_apply import router as apply_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
app = FastAPI(title="JobPilot API")
for r in (auth_router, cv_router, jobs_router, apps_router, integ_router, admin_router, phase2_router, coach_router,
          apply_router):
    app.include_router(r)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ["CORS_ORIGINS"].split(","),
                   allow_methods=["*"], allow_headers=["*"])
scheduler = AsyncIOScheduler()


@app.get("/api/health")
async def health():
    return {"ok": True}


async def seed_user(email, password, name, role):
    ex = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "password_hash": 1})
    # Admins are always on Premium. Write it on create as well as on update, otherwise a
    # first-boot admin is stored as "free" and /auth/me + the UI sidebar disagree with get_plan().
    extra = {"plan": "premium"} if role == "admin" else {}
    if not ex:
        await create_user(new_user_doc(email, name, password_hash=hash_password(password), role=role, onboarded=True,
                                       consents={"terms": True, "ai_processing": True, "email_messaging": False},
                                       **extra))
    else:
        upd = {"role": role, **extra}
        if not ex.get("password_hash") or not verify_password(password, ex["password_hash"]):
            upd["password_hash"] = hash_password(password)
        await db.users.update_one({"email": email}, {"$set": upd})


DEMO_CV = {
    "name": "Demo Seeker", "headline": "Senior Data Analyst",
    "contact": {"email": "demo@jobpilot.app", "phone": "+966500000000", "location": "Riyadh, Saudi Arabia", "links": []},
    "summary": "Data analyst with 6 years of experience turning operational data into decisions for retail and logistics teams in Saudi Arabia.",
    "experience": [
        {"company": "Almarai Company", "title": "Senior Data Analyst", "location": "Riyadh, Saudi Arabia",
         "start": "2022-03", "end": "Present",
         "bullets": ["Built the demand forecast used by 14 distribution centres, cutting stock-out incidents by 18%.",
                     "Automated the weekly sales reporting pack, saving about 12 hours of analyst time per week.",
                     "Partnered with finance on a margin model for 2,300 SKUs."]},
        {"company": "Jarir Holding", "title": "Data Analyst", "location": "Riyadh, Saudi Arabia",
         "start": "2019-06", "end": "2022-02",
         "bullets": ["Owned the SQL and Power BI layer behind store-level performance dashboards used by 90 managers.",
                     "Standardised KPI definitions across merchandising and supply chain, removing 3 competing versions of revenue."]},
    ],
    "education": [{"institution": "King Saud University", "degree": "Bachelor", "field": "Statistics", "start": "2014", "end": "2018"}],
    "skills": ["SQL", "Python", "Power BI", "Tableau", "dbt", "Snowflake", "forecasting", "A/B testing", "Arabic", "English"],
    "projects": [{"name": "GCC price index dashboard", "description": "Public-data dashboard comparing consumer prices across the six GCC states."}],
    "languages": [{"name": "Arabic", "level": "Native"}, {"name": "English", "level": "Professional working proficiency"}],
    "certifications": [{"name": "Google Data Analytics Professional Certificate", "issuer": "Google", "year": "2020"}],
}


async def seed_demo_cv(email):
    """Give the seeded demo account a master CV so a fresh database is usable immediately.

    Every AI feature (review, tailor, interview prep) requires a master CV, and the backend
    test suite asserts the demo user has one. Only runs when the user has no versions at all,
    so it never overwrites real edits.
    """
    user = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if not user:
        return
    if await db.cv_versions.find_one({"user_id": user["user_id"]}, {"_id": 0, "cv_version_id": 1}):
        return
    await db.cv_versions.insert_one({
        "cv_version_id": uid("cv_"), "user_id": user["user_id"], "version": 1, "data": DEMO_CV,
        "file_id": None, "note": "Seeded demo CV", "is_master": True, "created_at": iso()})
    logger.info(f"Seeded demo master CV for {email}")


async def seed():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.jobs.create_index("fingerprint")
    await db.jobs.create_index("job_id", unique=True)
    await db.jobs.create_index([("posted_at", -1)])
    await db.reviews.create_index([("user_id", 1), ("job_id", 1), ("cv_version_id", 1)])
    await db.ai_cache.create_index("key", unique=True)
    await db.reminders.create_index([("status", 1), ("deliver_at", 1)])
    await db.login_attempts.create_index("identifier")
    await db.applications.create_index([("user_id", 1), ("job_id", 1)])
    await db.apply_runs.create_index([("user_id", 1), ("created_at", -1)])
    await db.apply_profiles.create_index("user_id", unique=True)
    for p in DEFAULT_PLANS:
        await db.plans.update_one({"plan_id": p["plan_id"]}, {"$setOnInsert": p}, upsert=True)
    for s in DEFAULT_SOURCES:
        await db.sources.update_one({"source_id": s["source_id"]}, {"$setOnInsert": {**s, "enabled": True, "status": "idle"}}, upsert=True)
    await seed_user(os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"], "JobPilot Admin", "admin")
    demo_email = os.environ["TEST_USER_EMAIL"].lower()
    await seed_user(demo_email, os.environ["TEST_USER_PASSWORD"], "Demo Seeker", "user")
    await seed_demo_cv(demo_email)


@app.on_event("startup")
async def startup():
    await seed()
    try:
        init_storage()
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    scheduler.add_job(process_reminders, "interval", minutes=1, id="reminders", replace_existing=True, max_instances=1)
    scheduler.add_job(run_all_sources, "interval", hours=6, id="sources", replace_existing=True, max_instances=1)
    scheduler.add_job(ghost_check, "interval", hours=12, id="ghost", replace_existing=True, max_instances=1)
    scheduler.add_job(_scan_gmail_inbox, "interval", hours=1, id="gmail_scan", replace_existing=True, max_instances=1)
    scheduler.start()
    if await db.jobs.count_documents({}) == 0:
        scheduler.add_job(run_all_sources, id="initial_fetch", replace_existing=True)


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
    client.close()
