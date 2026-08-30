from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

app = FastAPI(
    title="Legal RAG API",
    description="Backend API for Vietnamese Legal Hybrid RAG System",
    version="1.0.0"
)

# CORS middleware for NextJS frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # NextJS default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routers import query

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "Legal RAG API is running"}

app.include_router(query.router, prefix="/api", tags=["rag"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Legal RAG API...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Legal RAG API...")
