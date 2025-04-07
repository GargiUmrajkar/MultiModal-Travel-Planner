from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.schemas import (
    TravelRequest, TravelResponse, FlightSearchRequest, 
    GroundTransportRequest, JourneyOptimizationRequest
)
from app.services.travel_service import TravelService
from typing import List, Dict, Optional
from datetime import date
import traceback
import asyncio
from fastapi.responses import JSONResponse

router = APIRouter()
travel_service = TravelService()

@router.post("/plan", response_model=TravelResponse)
async def plan_journey(request: TravelRequest):
    """
    Plan a journey with flights and ground transport
    """
    try:
        print("\n🚀 Received journey planning request:")
        print(f"From: {request.source_city}")
        print(f"To: {request.destination_city}")
        print(f"Departure: {request.depart_date}")
        print(f"Return: {request.return_date}")
        print(f"Optimization: {request.optimization_preference}")
        print(f"Budget: {request.budget}")

        # Validate dates
        print("\n📅 Validating dates...")
        if request.return_date <= request.depart_date:
            print("❌ Invalid dates: Return date must be after departure date")
            raise HTTPException(
                status_code=400,
                detail="Return date must be after departure date"
            )
        print("✅ Dates validated successfully")

        # Validate budget for cost optimization
        print("\n💰 Validating budget...")
        if request.optimization_preference == "cost" and not request.budget:
            print("❌ Missing budget for cost optimization")
            raise HTTPException(
                status_code=400,
                detail="Budget is required when optimizing for cost"
            )
        print("✅ Budget validation passed")

        print("\n🔄 Calling travel service plan_journey...")
        try:
            # Set a timeout for the entire operation
            result = await asyncio.wait_for(
                travel_service.plan_journey(
                    source_city=request.source_city,
                    destination_city=request.destination_city,
                    depart_date=request.depart_date,
                    return_date=request.return_date,
                    optimization_preference=request.optimization_preference,
                    budget=request.budget
                ),
                timeout=300000  # 30 seconds timeout
            )
        except asyncio.TimeoutError:
            print("❌ Operation timed out after 30 seconds")
            return JSONResponse(
                status_code=408,
                content={
                    "detail": "Request timed out. The journey planning is taking longer than expected. Please try with different dates or cities."
                }
            )

        if not result:
            print("❌ Travel service returned no results")
            raise HTTPException(
                status_code=404,
                detail="No valid travel combinations found"
            )

        print("\n✨ Successfully planned journey")
        print("Preferred journey details:")
        if result.preferred_journey:
            print(f"Total cost: ${result.preferred_journey.total_cost:.2f}")
            print(f"Total time: {result.preferred_journey.total_time} minutes")
            print(f"Flight cost: ${result.preferred_journey.flight_cost:.2f}")
            print(f"Ground cost: ${result.preferred_journey.ground_cost:.2f}")
        
        if result.alternative_journey:
            print("\nAlternative journey available")
        
        if result.available_bus_options:
            print("Bus options available")

        return result

    except ValueError as e:
        error_msg = str(e)
        print(f"\n❌ ValueError in plan_journey: {error_msg}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )
    except HTTPException as he:
        print(f"\n❌ HTTPException in plan_journey: {he.detail}")
        print(f"Status code: {he.status_code}")
        raise he
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Unexpected error in plan_journey: {error_msg}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {error_msg}"
        )

@router.get("/airports/{city}")
async def get_airports(city: str) -> List[str]:
    """
    Get major airports for a given city
    """
    try:
        print(f"\n🔍 Searching airports for: {city}")
        airports = await travel_service.get_airports(city)
        if not airports:
            print(f"❌ No airports found for {city}")
            raise HTTPException(
                status_code=404,
                detail=f"No major airports found for {city}"
            )
        print(f"✅ Found airports: {airports}")
        return airports
    except Exception as e:
        print(f"❌ Error getting airports for {city}: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/flights/search")
async def search_flights(request: FlightSearchRequest) -> Dict:
    """
    Search for flights between airports
    """
    try:
        print(f"\n✈️ Searching flights:")
        print(f"From: {request.from_airport}")
        print(f"To: {request.to_airport}")
        print(f"Date: {request.travel_date}")
        
        flights = await travel_service.search_flights(
            from_airport=request.from_airport,
            to_airport=request.to_airport,
            date=request.travel_date
        )
        if not flights:
            print("❌ No flights found")
            raise HTTPException(
                status_code=404,
                detail="No flights found for the specified route"
            )
        print("✅ Flights found successfully")
        return flights
    except Exception as e:
        print(f"❌ Error searching flights: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/ground-transport/search")
async def search_ground_transport(request: GroundTransportRequest) -> Dict:
    """
    Search for ground transport options
    """
    try:
        print(f"\n🚗 Searching ground transport:")
        print(f"From: {request.from_location}")
        print(f"To: {request.to_location}")
        print(f"Date: {request.travel_date}")
        print(f"Preferred time: {request.preferred_time}")
        
        transport_options = await travel_service.search_ground_transport(
            from_location=request.from_location,
            to_location=request.to_location,
            date=request.travel_date,
            preferred_time=request.preferred_time
        )
        if not transport_options:
            print("❌ No ground transport options found")
            raise HTTPException(
                status_code=404,
                detail="No ground transport options found"
            )
        print("✅ Ground transport options found")
        return transport_options
    except Exception as e:
        print(f"❌ Error searching ground transport: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/journey/optimize")
async def optimize_journey(request: JourneyOptimizationRequest) -> Dict:
    """
    Optimize journey combinations using AI
    """
    try:
        print("\n⚡ Optimizing journey:")
        print(f"Optimization preference: {request.optimization_preference}")
        print(f"Budget: {request.budget}")
        print(f"Number of flight options: {len(request.flight_options)}")
        print(f"Number of ground options: {len(request.ground_options)}")
        
        optimized_journey = await travel_service.optimize_journey(
            flight_options=request.flight_options,
            ground_options=request.ground_options,
            optimization_preference=request.optimization_preference,
            budget=request.budget
        )
        if not optimized_journey:
            print("❌ No optimized journey found")
            raise HTTPException(
                status_code=404,
                detail="Could not find an optimized journey combination"
            )
        print("✅ Journey optimized successfully")
        return optimized_journey
    except Exception as e:
        print(f"❌ Error optimizing journey: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 