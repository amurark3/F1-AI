"""
F1 AI Backend — Entry Point
============================
Boots the FastAPI application, configures CORS, and mounts the API router.

Environment variables required (place in a .env file in this directory):
  GOOGLE_API_KEY  — Google Generative AI (Gemini) API key
  TAVILY_API_KEY  — Tavily web-search API key
"""

from dotenv import load_dotenv

# Load .env BEFORE any other local imports so os.getenv() works everywhere.
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes

app = FastAPI(
    title="F1 AI Race Engineer",
    description="AI-powered Formula 1 race analysis and strategy assistant.",
    version="1.0.0",
)

# CORS — restrict origins to the frontend dev server.
# For production, replace with the deployed frontend URL or read from env.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")


@app.get("/")
def read_root():
    """Health probe for the root path."""
    return {"status": "Backend is running", "service": "F1 Race Engineer"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
