from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import travel

app = FastAPI(
    title="Travel Planner API",
    description="""
    Travel Planner API helps you find the best flight and ground transport combinations for your journey.
    
    Features:
    * Search for flights between cities
    * Find ground transport options
    * Optimize for cost or time
    * Get alternative journey suggestions
    * Find bus and train connections
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def root():
    """
    Root endpoint that provides API information and available endpoints
    """
    return JSONResponse({
        "name": "Travel Planner API",
        "version": "1.0.0",
        "description": "API for planning multi-city travel with flight and ground transport options",
        "endpoints": {
            "documentation": {
                "swagger": "/api/docs",
                "redoc": "/api/redoc"
            },
            "travel": {
                "plan_journey": "/api/v1/plan",
                "get_airports": "/api/v1/airports/{city}"
            }
        }
    })

# Include routers
app.include_router(travel.router, prefix="/api/v1", tags=["travel"]) 