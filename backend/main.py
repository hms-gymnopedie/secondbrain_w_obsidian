"""
Second Brain - FastAPI Backend
Main application entry point.
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers.upload import router as upload_router
from backend.services.obsidian_writer import init_vault

app = FastAPI(
    title="Second Brain API",
    description="Obsidian 기반 지식 구조화 시스템",
    version="1.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(upload_router)

# Serve frontend static files
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.on_event("startup")
async def startup_event():
    """Initialize vault on startup."""
    init_vault()
    settings.upload_abs_path.mkdir(parents=True, exist_ok=True)
    print(f"✅ Second Brain 서버 시작")
    print(f"   Vault: {settings.vault_abs_path}")
    print(f"   AI Provider: {settings.ai_provider}")
    print(f"   Dashboard: http://{settings.host}:{settings.port}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
