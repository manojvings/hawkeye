"""API v1 endpoints"""
from fastapi import APIRouter
from .endpoints import auth, users, organizations, cases, tasks, observables, alerts, case_templates, cortex

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(observables.router, prefix="/observables", tags=["observables"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(case_templates.router, prefix="/case-templates", tags=["case-templates"])
api_router.include_router(cortex.router, prefix="/cortex", tags=["cortex"])