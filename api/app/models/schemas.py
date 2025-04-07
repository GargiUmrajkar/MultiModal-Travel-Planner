from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import date, datetime

class TravelRequest(BaseModel):
    source_city: str = Field(..., description="Source city name")
    destination_city: str = Field(..., description="Destination city name")
    depart_date: date = Field(..., description="Departure date in YYYY-MM-DD format")
    return_date: date = Field(..., description="Return date in YYYY-MM-DD format")
    optimization_preference: Literal["cost", "time"] = Field(..., description="Optimization preference: cost or time")
    budget: Optional[float] = Field(None, description="Maximum budget (only required when optimizing for cost)")

class FlightSearchRequest(BaseModel):
    from_airport: str = Field(..., description="Source airport code")
    to_airport: str = Field(..., description="Destination airport code")
    travel_date: date = Field(..., description="Travel date in YYYY-MM-DD format")

class GroundTransportRequest(BaseModel):
    from_location: str = Field(..., description="Source location")
    to_location: str = Field(..., description="Destination location")
    travel_date: date = Field(..., description="Travel date in YYYY-MM-DD format")
    preferred_time: Optional[str] = Field(None, description="Preferred departure time (HH:MM format)")

class JourneyOptimizationRequest(BaseModel):
    flight_options: List[Dict] = Field(..., description="List of available flight options")
    ground_options: List[Dict] = Field(..., description="List of available ground transport options")
    optimization_preference: Literal["cost", "time"] = Field(..., description="Optimization preference: cost or time")
    budget: Optional[float] = Field(None, description="Maximum budget (only required when optimizing for cost)")

class GroundTransport(BaseModel):
    duration_mins: int
    cost_usd: float
    recommended_mode: str
    notes: str
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None

class FlightDetails(BaseModel):
    Price: str
    Origin: str
    Destination: str
    Departure: str
    Arrival: str
    Flight_Duration_mins: int = Field(alias="Flight Duration (mins)")
    Airline: str
    Stops: int

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True

class JourneySegment(BaseModel):
    ground_to_airport: GroundTransport
    flight: FlightDetails
    ground_from_airport: GroundTransport
    total_segment_time: int

class JourneyCombination(BaseModel):
    outbound: JourneySegment
    return_journey: JourneySegment
    total_cost: float
    total_time: int
    flight_cost: float
    ground_cost: float

class TravelResponse(BaseModel):
    preferred_journey: JourneyCombination
    alternative_journey: Optional[JourneyCombination] = None
    available_bus_options: Optional[dict] = None 