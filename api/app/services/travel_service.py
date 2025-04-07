from datetime import date
from typing import List, Optional, Dict
import asyncio
from app.models.schemas import TravelResponse, JourneyCombination, JourneySegment, GroundTransport, FlightDetails
import sys
import os
import traceback

# Add the root directory to Python path to import app_4
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from app_4 import (
    get_major_airports,
    search_flights,
    get_ground_transit_details,
    get_best_balanced_option,
    find_matching_ground_transport
)

def extract_flight_details(api_response, optimization_preference="cost"):
    """
    Extracts details of the best flight from the API response.
    Now considers optimization preference when selecting the best flight.
    """
    if not api_response or "data" not in api_response or "itineraries" not in api_response["data"]:
        return None

    flights = api_response["data"]["itineraries"]
    if not flights:
        return None

    # Select best flight based on optimization preference
    if optimization_preference == "time":
        best_flight = min(flights, key=lambda x: x["legs"][0]["durationInMinutes"])
    else:  # cost
        best_flight = min(flights, key=lambda x: x["price"]["raw"])
    
    # Enhanced carrier extraction
    carrier_name = "Unknown"
    try:
        if "carriers" in best_flight["legs"][0]:
            carriers = best_flight["legs"][0]["carriers"]
            if "marketing" in carriers and carriers["marketing"]:
                carrier_name = carriers["marketing"][0]["name"]
            elif "operating" in carriers and carriers["operating"]:
                carrier_name = carriers["operating"][0]["name"]
    except Exception as e:
        print(f"Error extracting carrier name: {e}")

    return {
        "Price": best_flight["price"]["formatted"],
        "Origin": best_flight["legs"][0]["origin"]["displayCode"],
        "Destination": best_flight["legs"][0]["destination"]["displayCode"],
        "Departure": best_flight["legs"][0]["departure"],
        "Arrival": best_flight["legs"][0]["arrival"],
        "Flight Duration (mins)": best_flight["legs"][0]["durationInMinutes"],
        "Airline": carrier_name,
        "Stops": best_flight["legs"][0]["stopCount"]
    }

class TravelService:
    def __init__(self):
        self._flight_cache = {}
        self._transit_cache = {}

    async def get_airports(self, city: str) -> List[str]:
        """
        Get major airports for a given city
        """
        try:
            # Set a timeout for airport search
            async with asyncio.timeout(5):  # 5 seconds timeout
                airports = get_major_airports(city)
                print(f"\n🔍 Raw airport response for {city}: {airports}")
                
                # Handle different response formats
                if isinstance(airports, dict):
                    # Handle case where response is a dict with airport_codes
                    return airports.get("airport_codes", [])
                elif isinstance(airports, list):
                    # Handle case where response is directly a list of airport codes
                    return airports
                else:
                    print(f"⚠️ Unexpected airport response format for {city}: {airports}")
                    return []
        except asyncio.TimeoutError:
            print(f"⚠️ Airport search timed out for {city}")
            return []
        except Exception as e:
            print(f"⚠️ Error getting airports for {city}: {str(e)}")
            return []

    async def _get_cached_flight(self, from_airport: str, to_airport: str, date: str, max_retries: int = 3):
        """Get flight details with caching and retries"""
        cache_key = f"{from_airport}-{to_airport}-{date}"
        if cache_key not in self._flight_cache:
            for attempt in range(max_retries):
                try:
                    # Set a timeout for the flight search
                    async with asyncio.timeout(10):  # 10 seconds timeout per attempt
                        response = search_flights(
                            "https://sky-scanner3.p.rapidapi.com/flights/search-one-way",
                            {"fromEntityId": from_airport, "toEntityId": to_airport, "departDate": date}
                        )
                        if response and "data" in response and "itineraries" in response["data"]:
                            # Store all flight options instead of just the cheapest one
                            self._flight_cache[cache_key] = response
                            break
                        else:
                            print(f"❌ No valid flight data found for {from_airport} to {to_airport}")
                            if attempt == max_retries - 1:
                                return None
                            await asyncio.sleep(1)
                except asyncio.TimeoutError:
                    print(f"⚠️ Flight search timed out (attempt {attempt + 1}/{max_retries})")
                    if attempt == max_retries - 1:
                        print("❌ All flight search attempts timed out")
                        return None
                    await asyncio.sleep(1)  # Short delay between retries
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(1)
        return self._flight_cache[cache_key]

    async def _get_cached_transit(self, from_loc: str, to_loc: str, date: str, preferred_time: Optional[str] = None):
        """Get ground transit details with caching"""
        cache_key = f"{from_loc}-{to_loc}-{date}-{preferred_time}"
        if cache_key not in self._transit_cache:
            try:
                # Set a timeout for ground transit search
                async with asyncio.timeout(5):  # 5 seconds timeout
                    self._transit_cache[cache_key] = get_ground_transit_details(
                        from_loc,
                        to_loc,
                        date,
                        preferred_time
                    )
            except asyncio.TimeoutError:
                print(f"⚠️ Ground transit search timed out for {from_loc} to {to_loc}")
                return None
        return self._transit_cache[cache_key]

    async def search_flights(self, from_airport: str, to_airport: str, date: date) -> Dict:
        """
        Search for flights between airports
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = f"{from_airport}-{to_airport}-{date_str}"
        
        if cache_key not in self._flight_cache:
            self._flight_cache[cache_key] = search_flights(
                "https://sky-scanner3.p.rapidapi.com/flights/search-one-way",
                {
                    "fromEntityId": from_airport,
                    "toEntityId": to_airport,
                    "departDate": date_str
                }
            )
        
        return self._flight_cache[cache_key]

    async def search_ground_transport(
        self,
        from_location: str,
        to_location: str,
        date: date,
        preferred_time: Optional[str] = None
    ) -> Dict:
        """
        Search for ground transport options
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = f"{from_location}-{to_location}-{date_str}-{preferred_time}"
        
        if cache_key not in self._transit_cache:
            self._transit_cache[cache_key] = get_ground_transit_details(
                from_location,
                to_location,
                date_str,
                preferred_time
            )
        
        return self._transit_cache[cache_key]

    async def optimize_journey(
        self,
        flight_options: List[Dict],
        ground_options: List[Dict],
        optimization_preference: str,
        budget: Optional[float] = None
    ) -> Dict:
        """
        Optimize journey combinations using AI
        """
        # Extract flight details
        flights = [extract_flight_details(flight, optimization_preference) for flight in flight_options]
        flights = [f for f in flights if f]  # Remove None values

        # Find matching ground transport
        ground_transport = []
        for flight in flights:
            transport = find_matching_ground_transport(
                flight,
                ground_options,
                optimization_preference
            )
            if transport:
                ground_transport.append(transport)

        # Get best balanced option
        return get_best_balanced_option(
            flights,
            ground_transport,
            optimization_preference,
            budget
        )

    async def plan_journey(
        self,
        source_city: str,
        destination_city: str,
        depart_date: date,
        return_date: date,
        optimization_preference: str,
        budget: Optional[float] = None
    ) -> TravelResponse:
        """
        Plan a complete journey including flights and ground transport
        """
        try:
            print(f"\n🔄 Starting journey planning for {source_city} to {destination_city}")
            print(f"Dates: {depart_date} to {return_date}")
            print(f"Optimization: {optimization_preference}, Budget: {budget}")

            # Convert dates to strings
            depart_date_str = depart_date.strftime("%Y-%m-%d")
            return_date_str = return_date.strftime("%Y-%m-%d")

            # Get airports
            print("\n🛫 Fetching airports...")
            source_airports = await self.get_airports(source_city)
            destination_airports = await self.get_airports(destination_city)

            print(f"Source airports found: {source_airports}")
            print(f"Destination airports found: {destination_airports}")

            if not source_airports or not destination_airports:
                raise ValueError("No valid airports found for source or destination")

            all_combinations = []

            # Find all valid combinations
            for src_airport in source_airports:
                print(f"\n🔍 Processing source airport: {src_airport}")
                try:
                    # Ground transport to departure airport
                    print(f"Getting ground transport: {source_city} → {src_airport} Airport")
                    source_to_airport = await self._get_cached_transit(
                        source_city,
                        f"{src_airport} Airport",
                        depart_date_str
                    )
                    if not source_to_airport:
                        print("❌ No ground transport found to departure airport")
                        continue
                    print("✅ Ground transport found to departure airport")

                    for dest_airport_in in destination_airports:
                        print(f"\n🔍 Processing destination airport: {dest_airport_in}")
                        try:
                            # Outbound flight
                            print(f"Searching flight: {src_airport} → {dest_airport_in}")
                            flight_to = await self._get_cached_flight(
                                src_airport,
                                dest_airport_in,
                                depart_date_str
                            )
                            if not flight_to:
                                print("❌ No outbound flight found")
                                continue

                            print("Extracting outbound flight details...")
                            outbound_flight = extract_flight_details(flight_to, optimization_preference)
                            if not outbound_flight:
                                print("❌ Could not extract outbound flight details")
                                continue
                            print(f"✅ Outbound flight found: {outbound_flight['Price']}")

                            # Ground transport from arrival airport to destination
                            print(f"Getting ground transport: {dest_airport_in} Airport → {destination_city}")
                            airport_to_dest = await self._get_cached_transit(
                                f"{dest_airport_in} Airport",
                                destination_city,
                                depart_date_str,
                                outbound_flight.get('arrival')
                            )
                            if not airport_to_dest:
                                print("❌ No ground transport found from arrival airport")
                                continue
                            print("✅ Ground transport found from arrival airport")

                            # Return journey - try all destination airports for return
                            for dest_airport_out in destination_airports:
                                print(f"\n🔍 Processing return from airport: {dest_airport_out}")
                                # Ground transport from destination to departure airport
                                print(f"Getting ground transport: {destination_city} → {dest_airport_out} Airport")
                                dest_to_airport = await self._get_cached_transit(
                                    destination_city,
                                    f"{dest_airport_out} Airport",
                                    return_date_str
                                )
                                if not dest_to_airport:
                                    print("❌ No ground transport found to return departure airport")
                                    continue
                                print("✅ Ground transport found to return departure airport")

                                # Return flight
                                print(f"Searching return flight: {dest_airport_out} → {src_airport}")
                                flight_return = await self._get_cached_flight(
                                    dest_airport_out,
                                    src_airport,
                                    return_date_str
                                )
                                if not flight_return:
                                    print("❌ No return flight found")
                                    continue

                                print("Extracting return flight details...")
                                return_flight = extract_flight_details(flight_return, optimization_preference)
                                if not return_flight:
                                    print("❌ Could not extract return flight details")
                                    continue
                                print(f"✅ Return flight found: {return_flight['Price']}")

                                # Ground transport from arrival airport back home
                                print(f"Getting ground transport: {src_airport} Airport → {source_city}")
                                airport_to_source = await self._get_cached_transit(
                                    f"{src_airport} Airport",
                                    source_city,
                                    return_date_str,
                                    return_flight.get('arrival')
                                )
                                if not airport_to_source:
                                    print("❌ No ground transport found from return arrival airport")
                                    continue
                                print("✅ Ground transport found from return arrival airport")

                                # Calculate costs
                                print("\n💰 Calculating costs...")
                                try:
                                    print(f"Outbound flight price: {outbound_flight['Price']}")
                                    print(f"Return flight price: {return_flight['Price']}")
                                    
                                    outbound_price = float(outbound_flight["Price"].replace('$', '').replace(',', ''))
                                    return_price = float(return_flight["Price"].replace('$', '').replace(',', ''))
                                    
                                    flight_cost = outbound_price + return_price
                                    ground_cost = (
                                        source_to_airport['cost_usd'] +
                                        airport_to_dest['cost_usd'] +
                                        dest_to_airport['cost_usd'] +
                                        airport_to_source['cost_usd']
                                    )
                                    total_cost = flight_cost + ground_cost

                                    print(f"Flight cost: ${flight_cost}")
                                    print(f"Ground cost: ${ground_cost}")
                                    print(f"Total cost: ${total_cost}")

                                    # Calculate total time
                                    total_time = (
                                        source_to_airport['duration_mins'] +
                                        outbound_flight['Flight Duration (mins)'] +
                                        airport_to_dest['duration_mins'] +
                                        dest_to_airport['duration_mins'] +
                                        return_flight['Flight Duration (mins)'] +
                                        airport_to_source['duration_mins']
                                    )

                                    # Create journey combination
                                    outbound_segment_time = (
                                        source_to_airport['duration_mins'] +
                                        outbound_flight['Flight Duration (mins)'] +
                                        airport_to_dest['duration_mins']
                                    )
                                    return_segment_time = (
                                        dest_to_airport['duration_mins'] +
                                        return_flight['Flight Duration (mins)'] +
                                        airport_to_source['duration_mins']
                                    )
                                    
                                    combination = JourneyCombination(
                                        outbound=JourneySegment(
                                            ground_to_airport=GroundTransport(**source_to_airport),
                                            flight=FlightDetails(**outbound_flight),
                                            ground_from_airport=GroundTransport(**airport_to_dest),
                                            total_segment_time=outbound_segment_time
                                        ),
                                        return_journey=JourneySegment(
                                            ground_to_airport=GroundTransport(**dest_to_airport),
                                            flight=FlightDetails(**return_flight),
                                            ground_from_airport=GroundTransport(**airport_to_source),
                                            total_segment_time=return_segment_time
                                        ),
                                        total_cost=total_cost,
                                        total_time=total_time,
                                        flight_cost=flight_cost,
                                        ground_cost=ground_cost
                                    )
                                    print("✅ Journey combination created successfully")
                                    all_combinations.append(combination)
                                    
                                    print("\n📋 Journey Summary:")
                                    print(f"Outbound: {source_city} → {src_airport} → {dest_airport_in} → {destination_city}")
                                    print(f"Return: {destination_city} → {dest_airport_out} → {src_airport} → {source_city}")
                                    print(f"Total Cost: ${total_cost:.2f}")
                                    print(f"Total Time: {total_time} minutes")

                                except Exception as e:
                                    print(f"❌ Error processing combination: {str(e)}")
                                    print(f"Traceback: {traceback.format_exc()}")
                                    continue

                        except Exception as e:
                            print(f"❌ Error processing destination airport {dest_airport_in}: {str(e)}")
                            continue

                except Exception as e:
                    print(f"❌ Error processing source airport {src_airport}: {str(e)}")
                    continue

            if not all_combinations:
                raise ValueError("No valid travel combinations found")

            print(f"\n✨ Found {len(all_combinations)} valid combinations")

            # Get preferred option based on optimization preference
            if optimization_preference == "cost":
                # For cost optimization, consider all combinations within budget + $100
                max_budget = budget + 100 if budget else float('inf')
                valid_combinations = [combo for combo in all_combinations if combo.total_cost <= max_budget]
                if not valid_combinations:
                    raise ValueError("No combinations found within budget")
                
                # Sort by cost and get cheapest as preferred
                valid_combinations.sort(key=lambda x: x.total_cost)
                preferred_journey = valid_combinations[0]
                
                # Find balanced alternative (faster but within budget + $100)
                alternative_journey = None
                if len(valid_combinations) > 1:
                    print(f"\n🔍 Searching for balanced alternatives among {len(valid_combinations)-1} other options")
                    
                    # Find options that provide good value for time saved
                    balanced_candidates = [
                        opt for opt in valid_combinations[1:]  # Skip the cheapest option
                        if (preferred_journey.total_time - opt.total_time > 90 and  # Must save at least 90 mins
                            opt.total_cost <= max_budget and  # Must be within budget
                            (opt.total_cost - preferred_journey.total_cost) / 
                            (preferred_journey.total_time - opt.total_time) <= 1.0)  # Cost per minute saved <= $1
                    ]
                    
                    print(f"Found {len(balanced_candidates)} balanced candidates")
                    if balanced_candidates:
                        # Find the option with the best time savings per cost ratio
                        alternative_journey = min(balanced_candidates, 
                            key=lambda x: (x.total_cost - preferred_journey.total_cost) / 
                                        (preferred_journey.total_time - x.total_time))
                        time_saved = preferred_journey.total_time - alternative_journey.total_time
                        cost_increase = alternative_journey.total_cost - preferred_journey.total_cost
                        
                        print(f"💡 Selected balanced alternative:")
                        print(f"- Time saved: {time_saved} minutes")
                        print(f"- Cost increase: ${cost_increase:.2f}")
                        print(f"- Cost per minute saved: ${(cost_increase/time_saved):.2f}")
                    else:
                        print("\n💡 No faster alternatives found with good value for money")
            else:  # time optimization
                # For time optimization, consider all combinations within budget + $100
                max_budget = budget + 100 if budget else float('inf')
                valid_combinations = [combo for combo in all_combinations if combo.total_cost <= max_budget]
                
                # Sort by total time and get fastest as preferred
                valid_combinations.sort(key=lambda x: x.total_time)
                preferred_journey = valid_combinations[0]
                
                # Find balanced alternative (cheaper but reasonably slower)
                alternative_journey = None
                if len(valid_combinations) > 1:
                    print(f"\n🔍 Searching for balanced alternatives among {len(valid_combinations)-1} other options")
                    
                    # Calculate cost savings per minute added for each option
                    for opt in valid_combinations[1:]:  # Skip the fastest option
                        time_increase = opt.total_time - preferred_journey.total_time
                        cost_savings = preferred_journey.total_cost - opt.total_cost
                        if cost_savings > 0:
                            savings_per_minute = cost_savings / time_increase if time_increase > 0 else float('inf')
                            print(f"Option: {opt.total_time} mins, ${opt.total_cost}")
                            print(f"Time increase: {time_increase} mins, Cost savings: ${cost_savings:.2f}")
                            print(f"Savings per extra minute: ${savings_per_minute:.2f}")
                    
                    # Find options that provide good value in cost savings
                    balanced_candidates = [
                        opt for opt in valid_combinations[1:]  # Skip the fastest option
                        if (opt.total_time <= preferred_journey.total_time + 180 and  # At most 3 hours slower
                            preferred_journey.total_cost - opt.total_cost >= 100 and  # Save at least $100
                            (preferred_journey.total_cost - opt.total_cost) / 
                            (opt.total_time - preferred_journey.total_time) >= 0.5)  # Save at least $0.50 per extra minute
                    ]
                    
                    print(f"Found {len(balanced_candidates)} balanced candidates")
                    if balanced_candidates:
                        # Find the option with the best cost savings per extra minute
                        alternative_journey = max(balanced_candidates, 
                            key=lambda x: (preferred_journey.total_cost - x.total_cost) / 
                                        (x.total_time - preferred_journey.total_time))
                        time_increase = alternative_journey.total_time - preferred_journey.total_time
                        cost_savings = preferred_journey.total_cost - alternative_journey.total_cost
                        
                        print(f"💡 Selected balanced alternative:")
                        print(f"- Additional time: {time_increase} minutes")
                        print(f"- Cost savings: ${cost_savings:.2f}")
                        print(f"- Savings per extra minute: ${(cost_savings/time_increase):.2f}")
                    else:
                        print("\n💡 No cheaper alternatives found with good value for money")

            # Get bus options if needed
            print("\n🚌 Getting bus options...")
            available_bus_options = None  # Implement bus search if needed

            return TravelResponse(
                preferred_journey=preferred_journey,
                alternative_journey=alternative_journey,
                available_bus_options=available_bus_options
            )

        except Exception as e:
            print(f"❌ Error in journey planning: {str(e)}")
            print(f"Traceback:\n{traceback.format_exc()}")
            raise e

    def _create_journey_combination(
        self,
        source_to_airport: Dict,
        outbound_flight: Dict,
        airport_to_dest: Dict,
        dest_to_airport: Dict,
        return_flight: Dict,
        airport_to_source: Dict,
        total_cost: float,
        flight_cost: float,
        ground_cost: float
    ) -> JourneyCombination:
        """
        Create a JourneyCombination object from the given components
        """
        return JourneyCombination(
            outbound=self._create_journey_segment(
                source_to_airport,
                outbound_flight,
                airport_to_dest
            ),
            return_journey=self._create_journey_segment(
                dest_to_airport,
                return_flight,
                airport_to_source
            ),
            total_cost=total_cost,
            total_time=sum([
                source_to_airport["duration_mins"],
                outbound_flight["Flight Duration (mins)"],
                airport_to_dest["duration_mins"],
                dest_to_airport["duration_mins"],
                return_flight["Flight Duration (mins)"],
                airport_to_source["duration_mins"]
            ]),
            flight_cost=flight_cost,
            ground_cost=ground_cost
        )

    def _get_preferred_option(
        self,
        combinations: List[JourneyCombination],
        preference: str
    ) -> JourneyCombination:
        """
        Get the preferred option based on optimization preference
        """
        if preference == "cost":
            return min(combinations, key=lambda x: x.total_cost)
        else:  # preference == "time"
            return min(combinations, key=lambda x: x.total_time)

    async def _get_bus_options(
        self,
        from_location: str,
        to_location: str,
        date: str,
        preferred_time: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get available bus options for a journey segment
        """
        try:
            return find_matching_ground_transport(
                preferred_time,
                from_location,
                to_location,
                date,
                "cost"  # Default to cost optimization for bus options
            )
        except Exception:
            return None

    def _create_journey_segment(
        self,
        ground_to: Dict,
        flight: Dict,
        ground_from: Dict
    ) -> JourneySegment:
        """
        Create a JourneySegment object from the given components
        """
        return JourneySegment(
            ground_to_airport=GroundTransport(
                duration_mins=ground_to["duration_mins"],
                cost_usd=ground_to["cost_usd"],
                recommended_mode=ground_to["recommended_mode"],
                notes=ground_to["notes"],
                departure_time=ground_to.get("departure_time"),
                arrival_time=ground_to.get("arrival_time")
            ),
            flight=FlightDetails(
                Price=flight["Price"],
                Origin=flight["Origin"],
                Destination=flight["Destination"],
                Departure=flight["Departure"],
                Arrival=flight["Arrival"],
                **{"Flight Duration (mins)": flight["Flight Duration (mins)"]},
                Airline=flight["Airline"],
                Stops=flight["Stops"]
            ),
            ground_from_airport=GroundTransport(
                duration_mins=ground_from["duration_mins"],
                cost_usd=ground_from["cost_usd"],
                recommended_mode=ground_from["recommended_mode"],
                notes=ground_from["notes"],
                departure_time=ground_from.get("departure_time"),
                arrival_time=ground_from.get("arrival_time")
            ),
            total_segment_time=(
                ground_to["duration_mins"] +
                flight["Flight Duration (mins)"] +
                ground_from["duration_mins"]
            )
        ) 