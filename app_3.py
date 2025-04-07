import os
from dotenv import load_dotenv
from openai import OpenAI
import json
import requests
from datetime import datetime

# Load environment variables
load_dotenv()

# Get API keys from environment variables
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
RAPIDAPI_HOST = os.getenv('RAPIDAPI_HOST')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
# GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

# Validate required environment variables
if not all([RAPIDAPI_KEY, OPENAI_API_KEY, RAPIDAPI_HOST]):
    raise ValueError("Missing required API keys in environment variables. Please check your .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

### **STEP 1: Get Valid Airports Using OpenAI**
def get_major_airports(location):
    """
    Uses OpenAI to:
    1. Check if the location has an airport.
    2. If yes, verify if it is a **major airport**.
    3. If not, find **nearby major airports** (ignoring municipal/small airports).
    """

    prompt = f"""
    Given the location "{location}", return a JSON object:
    - If the location has a **major** airport (international or large regional), return it.
    - If the location **only has a small municipal/private airport**, return nearby **major** airports instead.
    - Do **not** return small municipal or private airports.
    - Limit results to a **4-5 hour drive**.

    **Response Format:**
    {{
        "has_major_airport": true/false,
        "airport_codes": ["JFK", "ORD"]
    }}
    """

    try:
        response = client.chat.completions.create(model="gpt-4-0613",
        messages=[
            {"role": "system", "content": "You are a travel assistant that provides only **major** airport codes in JSON format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0)

        # Debugging: Print raw OpenAI response
        raw_response = response.choices[0].message.content
        print(f"\n🔍 OpenAI Raw Response for '{location}':\n{raw_response}\n")

        # Parse JSON response correctly
        airport_data = json.loads(raw_response.strip())

        # Return all major airports instead of just the primary one
        if airport_data.get("has_major_airport") and airport_data.get("airport_codes"):
            return airport_data["airport_codes"]  # Return all airport codes

        # Otherwise, return nearby major airports
        return airport_data.get("airport_codes", [])

    except json.JSONDecodeError as e:
        print(f"⚠️ JSON Parsing Error: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Error in OpenAI request: {e}")
        return []


### **STEP 2: Search Flights (Handles Empty Results)**
def search_flights(url, querystring):
    """
    Generic function to search for flights (handles both round-trip and one-way).
    """
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        # First verify API key is valid
        verify_url = "https://sky-scanner3.p.rapidapi.com/flights/get-status"
        verify_response = requests.get(verify_url, headers=headers, timeout=300000)
        if verify_response.status_code == 403:
            print("❌ API Key is invalid or expired. Please check your RapidAPI subscription.")
            return None
        
        # Proceed with flight search with increased timeout
        print(f"\n🔍 Searching flights with parameters: {querystring}")
        response = requests.get(url, headers=headers, params=querystring, timeout=300000)
        
        if response.status_code != 200:
            print(f"❌ API returned status code {response.status_code}")
            print(f"Error message: {response.text}")
            return None
            
        data = response.json()
        
        if not data:
            print("❌ API returned empty response")
            return None

        if "data" in data and "itineraries" in data["data"]:
            print(f"✅ Found {len(data['data']['itineraries'])} flight options")
            return data
        else:
            print(f"⚠️ No valid flight data found for {querystring}")
            print(f"API Response structure: {list(data.keys())}")
            return None

    except requests.exceptions.Timeout:
        print("❌ API Request timed out. The server took too long to respond.")
        print("Try again in a few minutes or check if the route exists.")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ Connection error. Please check your internet connection.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ API Request Failed: {str(e)}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return None


### **STEP 2: Get Transit Estimates**
def get_ground_transit_details(from_location, to_location):
    """
    Get ground transportation details between two locations
    Could be city→airport or airport→city
    """
    prompt = f"""
    Estimate ground transportation details from {from_location} to {to_location}.
    Consider:
    1. For journeys > 60 minutes: ALWAYS recommend bus/train as the primary option
    2. For journeys ≤ 60 minutes: cab can be recommended
    3. Typical duration accounting for traffic
    4. Approximate cost in USD (buses should be significantly cheaper than cabs for long distances)
    5. Time of day variations if significant

    Return ONLY a JSON object in this exact format:
    {{
        "duration_mins": 60,
        "cost_usd": 30,
        "recommended_mode": "bus",
        "notes": "Regular shuttle service available"
    }}

    IMPORTANT RULES:
    - If duration > 60 minutes, recommended_mode MUST be "bus" or "train"
    - Bus/train costs should be 30-40% of equivalent cab fare for long distances
    - Include frequency of service in notes for bus/train options
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-0613",
            messages=[
                {"role": "system", "content": "You are a local transport expert. Respond ONLY with the exact JSON format specified."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        transit_data = json.loads(response.choices[0].message.content.strip())
        print(f"✅ Got transit details for {from_location} → {to_location}")
        return transit_data
    except Exception as e:
        print(f"⚠️ Error getting ground transit details for {from_location} → {to_location}: {e}")
        # Default values now consider journey length
        duration = 60
        return {
            "duration_mins": duration,
            "cost_usd": 30 if duration <= 60 else 15,  # Cheaper for longer journeys
            "recommended_mode": "cab" if duration <= 60 else "bus",
            "notes": "Using default values due to error"
        }


def get_transit_options(start_location, end_location, travel_date):
    """
    Uses OpenAI to get the best bus and cab options for travel between two locations.
    """
    prompt = f"""
    Provide the best available **bus and cab options** for traveling from {start_location} to {end_location} on {travel_date}.
    Include:
    - Bus departure times that match flight arrival/departure times (there should be considerate time to reach the airport/leave from the airport to catch the bus).
    - Bus duration in minutes.
    - Bus ticket price (USD).
    - If the distance is under 2 hours, also provide a **cab option** with estimated cost and travel time.
    
    Response format:
    {{
        "bus": {{
            "departure_time": "HH:MM AM/PM",
            "duration_mins": <integer>,
            "price_usd": <integer>
        }},
        "cab": {{
            "duration_mins": <integer>,
            "price_usd": <integer>
        }}
    }}
    """

    try:
        response = client.chat.completions.create(model="gpt-4-0613",
        messages=[{"role": "system", "content": "You estimate bus and cab options in JSON format."},
                  {"role": "user", "content": prompt}],
        temperature=0)

        transit_data = json.loads(response.choices[0].message.content.strip())
        return transit_data

    except Exception:
        return None



### **STEP 4: Extract Flight Details**
def extract_flight_details(api_response):
    """
    Extracts details of the best flight from the API response.
    """
    if not api_response or "data" not in api_response or "itineraries" not in api_response["data"]:
        return None

    flights = api_response["data"]["itineraries"]
    if not flights:
        return None

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


### **STEP 5: Get the Best Balanced Option using OpenAI**
def get_best_balanced_option(flights):
    """
    Find the best balanced option considering multiple factors:
    1. Cost-Time Balance: Weighted based on how extreme the differences are
    2. Airport Consistency: Only penalize different airports if time savings isn't significant
    3. Flight Time Impact: Heavily penalize options with much longer flight times
    4. Total Journey Efficiency: Consider both ground and flight time together
    """
    if not flights:
        return None

    # Find min and max values for normalization
    min_cost = min(flights, key=lambda x: x["total_cost"])["total_cost"]
    max_cost = max(flights, key=lambda x: x["total_cost"])["total_cost"]
    min_time = min(flights, key=lambda x: x["total_time"])["total_time"]
    max_time = max(flights, key=lambda x: x["total_time"])["total_time"]

    # Get flight-specific min/max for separate analysis
    min_flight_time = min(flights, key=lambda x: (
        x["outbound"]["flight"]["Flight Duration (mins)"] + 
        x["return"]["flight"]["Flight Duration (mins)"]
    ))
    max_flight_time = max(flights, key=lambda x: (
        x["outbound"]["flight"]["Flight Duration (mins)"] + 
        x["return"]["flight"]["Flight Duration (mins)"]
    ))
    
    # Avoid division by zero
    cost_range = max_cost - min_cost if max_cost != min_cost else 1
    time_range = max_time - min_time if max_time != min_time else 1

    for flight in flights:
        # 1. Basic cost and time scores (normalized to 0-1)
        cost_score = (flight["total_cost"] - min_cost) / cost_range
        time_score = (flight["total_time"] - min_time) / time_range
        
        # 2. Calculate flight time ratio
        flight_time = (flight["outbound"]["flight"]["Flight Duration (mins)"] + 
                      flight["return"]["flight"]["Flight Duration (mins)"])
        min_total_flight_time = (min_flight_time["outbound"]["flight"]["Flight Duration (mins)"] + 
                               min_flight_time["return"]["flight"]["Flight Duration (mins)"])
        flight_time_ratio = flight_time / min_total_flight_time
        
        # Heavily penalize flights that are more than 50% longer than the shortest flight time
        flight_time_penalty = max(0, (flight_time_ratio - 1.5) * 2) if flight_time_ratio > 1.5 else 0
        
        # 3. Airport consistency score - but only if time savings isn't significant
        uses_same_airport = flight["outbound"]["flight"]["Destination"] == flight["return"]["flight"]["Origin"]
        time_savings = max_time - flight["total_time"]
        time_savings_significant = time_savings > (max_time - min_time) * 0.2  # 20% threshold
        
        # Only penalize different airports if time savings isn't significant
        airport_penalty = 0 if (uses_same_airport or time_savings_significant) else 0.15
        
        # 4. Ground transport efficiency
        ground_time = flight["total_time"] - flight_time
        ground_ratio = ground_time / flight["total_time"]
        ground_penalty = max(0, (ground_ratio - 0.4) * 2) if ground_ratio > 0.4 else 0  # Penalize if ground time > 40% of total
        
        # 5. Calculate final balanced score with dynamic weights
        # If cost difference is small (<15%), prioritize time more
        cost_diff_ratio = (flight["total_cost"] - min_cost) / min_cost
        if cost_diff_ratio < 0.15:  # If cost difference is less than 15%
            cost_weight = 0.25
            time_weight = 0.45
        else:
            cost_weight = 0.35
            time_weight = 0.35
            
        flight["balanced_score"] = (
            cost_weight * cost_score +           # Cost weight
            time_weight * time_score +           # Time weight
            0.2 * flight_time_penalty +          # Flight time efficiency
            airport_penalty +                    # Airport consistency
            0.1 * ground_penalty                 # Ground transport efficiency
        )

    # Return the option with the best balanced score
    return min(flights, key=lambda x: x["balanced_score"])


### **STEP 1: Get Bus Options from OpenAI**
def get_bus_options(start_location, end_location, travel_date, preferred_time):
    """
    Fetches bus schedules, duration, and prices using OpenAI.
    """
    prompt = f"""
    Find bus options from {start_location} to {end_location} on {travel_date}.
    Provide:
    - Departure Time
    - Arrival Time
    - Duration in minutes
    - Price in USD
    - Bus Company Name (FlixBus, Greyhound, Wanderu, etc.)

    Select options where departure is closest to {preferred_time}.
    
    **Response Format (JSON):**
    {{
        "buses": [
            {{"company": "FlixBus", "departure": "14:00", "arrival": "18:30", "duration_mins": 270, "price": 35}},
            {{"company": "Greyhound", "departure": "15:00", "arrival": "19:30", "duration_mins": 270, "price": 38}}
        ]
    }}
    """

    try:
        response = client.chat.completions.create(model="gpt-4-0613",
        messages=[{"role": "user", "content": prompt}],
        temperature=0)
        bus_data = json.loads(response.choices[0].message.content.strip())
        return bus_data.get("buses", [])
    except Exception:
        return []


### **STEP 2: Get Cab Estimate**
def get_cab_estimate(start_location, end_location):
    """
    Uses OpenAI to estimate cab fare and travel time.
    """
    prompt = f"""
    Estimate cab fare and duration in minutes from {start_location} to {end_location}.
    **Response Format (JSON):**
    {{
        "cab_time_mins": <integer>,
        "cab_fare_usd": <integer>
    }}
    """

    try:
        response = client.chat.completions.create(model="gpt-4-0613",
        messages=[{"role": "user", "content": prompt}],
        temperature=0)
        cab_data = json.loads(response.choices[0].message.content.strip())
        return cab_data.get("cab_time_mins", 0), cab_data.get("cab_fare_usd", 0)
    except Exception:
        return 0, 0


### **STEP 3: Main Function**
def main():
    # Get user inputs
    source_city = input("Enter source city: ").strip()
    destination_city = input("Enter destination city: ").strip()
    depart_date = input("Enter departure date (YYYY-MM-DD): ").strip()
    return_date = input("Enter return date (YYYY-MM-DD): ").strip()
    preference = input("Do you want to optimize for (cost/time)? ").strip().lower()
    
    while preference not in ["cost", "time"]:
        print("Please enter either 'cost' or 'time'")
        preference = input("Do you want to optimize for (cost/time)? ").strip().lower()

    # Only ask for budget if optimizing for cost
    budget = float('inf')  # Default to no budget limit
    if preference == "cost":
        budget = float(input("Enter your maximum budget: "))

    # Get airports for both cities
    source_airports = get_major_airports(source_city)
    destination_airports = get_major_airports(destination_city)

    if not source_airports or not destination_airports:
        print("❌ No valid airports found for source or destination. Try again.")
        return

    print("\n🔄 Analyzing all possible combinations...")
    all_combinations = []
    
    # Cache for flight searches to avoid redundant API calls
    flight_cache = {}
    
    # Cache for ground transit details to avoid redundant GPT calls
    transit_cache = {}

    def get_cached_flight(from_airport, to_airport, date):
        cache_key = f"{from_airport}-{to_airport}-{date}"
        if cache_key not in flight_cache:
            flight_cache[cache_key] = search_flights(
                "https://sky-scanner3.p.rapidapi.com/flights/search-one-way",
                {"fromEntityId": from_airport, "toEntityId": to_airport, "departDate": date}
            )
        return flight_cache[cache_key]

    def get_cached_transit(from_loc, to_loc):
        cache_key = f"{from_loc}-{to_loc}"
        if cache_key not in transit_cache:
            transit_cache[cache_key] = get_ground_transit_details(from_loc, to_loc)
        return transit_cache[cache_key]

    for src_airport in source_airports:
        source_to_airport = get_cached_transit(source_city, f"{src_airport} Airport")
        
        for dest_airport_in in destination_airports:
            flight_to = get_cached_flight(src_airport, dest_airport_in, depart_date)
            if not flight_to:
                continue
                
            airport_to_dest = get_cached_transit(f"{dest_airport_in} Airport", destination_city)
            
            for dest_airport_out in destination_airports:
                dest_to_airport = get_cached_transit(destination_city, f"{dest_airport_out} Airport")
                
                flight_back = get_cached_flight(dest_airport_out, src_airport, return_date)
                if not flight_back:
                    continue
                
                airport_to_source = get_cached_transit(f"{src_airport} Airport", source_city)
                
                outbound_flight = extract_flight_details(flight_to)
                return_flight = extract_flight_details(flight_back)
                
                if outbound_flight and return_flight:
                    # Calculate total costs and times
                    flight_cost = (float(outbound_flight["Price"].replace("$", "")) + 
                                 float(return_flight["Price"].replace("$", "")))
                    ground_cost = (source_to_airport["cost_usd"] + airport_to_dest["cost_usd"] +
                                 dest_to_airport["cost_usd"] + airport_to_source["cost_usd"])
                    total_cost = flight_cost + ground_cost
                    
                    flight_time = outbound_flight["Flight Duration (mins)"] + return_flight["Flight Duration (mins)"]
                    ground_time = (source_to_airport["duration_mins"] + airport_to_dest["duration_mins"] +
                                 dest_to_airport["duration_mins"] + airport_to_source["duration_mins"])
                    total_time = flight_time + ground_time

                    # For time optimization, include all combinations
                    # For cost optimization, only include if within budget
                    if preference == "time" or total_cost <= budget:
                        combination = {
                            "outbound": {
                                "ground_to_airport": source_to_airport,
                                "flight": outbound_flight,
                                "ground_from_airport": airport_to_dest,
                                "total_segment_time": (source_to_airport["duration_mins"] + 
                                                     outbound_flight["Flight Duration (mins)"] + 
                                                     airport_to_dest["duration_mins"])
                            },
                            "return": {
                                "ground_to_airport": dest_to_airport,
                                "flight": return_flight,
                                "ground_from_airport": airport_to_source,
                                "total_segment_time": (dest_to_airport["duration_mins"] + 
                                                     return_flight["Flight Duration (mins)"] + 
                                                     airport_to_source["duration_mins"])
                            },
                            "total_cost": total_cost,
                            "total_time": total_time,
                            "flight_cost": flight_cost,
                            "ground_cost": ground_cost
                        }
                        all_combinations.append(combination)
                        print(f"\n✈️ Found valid combination:")
                        print(f"Outbound: {source_city} → {outbound_flight['Origin']} → {outbound_flight['Destination']} → {destination_city}")
                        print(f"Return: {destination_city} → {return_flight['Origin']} → {return_flight['Destination']} → {source_city}")
                        print(f"Total Cost: ${total_cost:.2f} (Flight: ${flight_cost:.2f}, Ground: ${ground_cost:.2f})")
                        print(f"Total Time: {total_time} minutes")

    if not all_combinations:
        if preference == "cost":
            print("❌ No valid combinations found within your budget.")
        else:
            print("❌ No valid combinations found.")
        return

    print(f"\n🎯 Found {len(all_combinations)} valid combinations")

    # Get user's preferred option based on their choice
    if preference == "cost":
        preferred_option = min(all_combinations, key=lambda x: x["total_cost"])
        print("\n💰 Best Option by Cost (Your Preference):")
    else:  # time
        # First find the fastest flight combination
        preferred_option = min(all_combinations, 
            key=lambda x: (x["outbound"]["flight"]["Flight Duration (mins)"] + 
                         x["return"]["flight"]["Flight Duration (mins)"])
        )
        print("\n⚡ Best Option by Time (Your Preference):")

    # Print preferred option summary
    print("\n📋 Your Preferred Journey Summary:")
    print_journey_summary(preferred_option, source_city, destination_city)

    # For time optimization, look for cheaper alternatives that are only slightly slower
    if preference == "time":
        fastest_flight_time = (preferred_option["outbound"]["flight"]["Flight Duration (mins)"] + 
                             preferred_option["return"]["flight"]["Flight Duration (mins)"])
        
        # Look for options that are at most 60 minutes slower in flight time but at least $100 cheaper
        balanced_candidates = [
            opt for opt in all_combinations
            if (opt["outbound"]["flight"]["Flight Duration (mins)"] + 
                opt["return"]["flight"]["Flight Duration (mins)"]) <= fastest_flight_time + 60 and  # At most 1 hour slower
            opt["total_cost"] < preferred_option["total_cost"] - 100  # At least $100 cheaper
        ]
        
        if balanced_candidates:
            balanced_option = min(balanced_candidates, key=lambda x: x["total_cost"])
            flight_time_diff = ((balanced_option["outbound"]["flight"]["Flight Duration (mins)"] + 
                               balanced_option["return"]["flight"]["Flight Duration (mins)"]) - 
                              fastest_flight_time)
            cost_savings = preferred_option["total_cost"] - balanced_option["total_cost"]
            
            print("\n💡 Cost-Effective Alternative:")
            print(f"Found an option that trades some speed for significant savings:")
            print(f"- Flight time difference: +{flight_time_diff} minutes")
            print(f"- Cost savings: ${cost_savings:.2f}")
            if flight_time_diff > 0:
                print(f"- Cost savings per extra minute: ${(cost_savings/flight_time_diff):.2f}")
            print_journey_summary(balanced_option, source_city, destination_city)
        else:
            print("\n⚖️ Time Analysis:")
            print("This is the optimal option because:")
            
            # Compare flight times with other options
            other_flight_times = [(opt["outbound"]["flight"]["Flight Duration (mins)"] + 
                                 opt["return"]["flight"]["Flight Duration (mins)"]) 
                                for opt in all_combinations if opt != preferred_option]
            
            if other_flight_times:  # Check if there are other options to compare against
                next_fastest_time = min(other_flight_times)
                time_difference = next_fastest_time - fastest_flight_time
                print(f"- It has the fastest flight time, saving {time_difference} minutes over the next fastest option")
            
            # Check if it uses efficient airports
            if preferred_option["outbound"]["flight"]["Destination"] == preferred_option["return"]["flight"]["Origin"]:
                print("- It uses the same airport for arrival and departure, minimizing ground transport")
            
            # Check if ground transport is reasonable
            ground_time = preferred_option["total_time"] - fastest_flight_time
            if ground_time <= 450:  # 7.5 hours total ground time is reasonable for this route
                print("- Ground transport time is reasonable for this route")
            
            # Check if it's also cost-effective
            sorted_by_cost = sorted(all_combinations, key=lambda x: x["total_cost"])
            cost_rank = sorted_by_cost.index(preferred_option) + 1
            if cost_rank <= len(all_combinations) // 2:
                print(f"- It's also among the cheaper options (#{cost_rank} out of {len(all_combinations)} by cost)")
    else:
        # Use existing balanced option logic for cost optimization
        balanced_option = get_best_balanced_option(all_combinations)
        if balanced_option and balanced_option != preferred_option:
            time_diff = preferred_option["total_time"] - balanced_option["total_time"]
            cost_diff = balanced_option["total_cost"] - preferred_option["total_cost"]
            
            # Only show if there's a meaningful trade-off
            if time_diff > 90 or (time_diff > 0 and cost_diff / time_diff < 0.5):
                print("\n⚖️ Alternative Balanced Option:")
                print(f"Found an option that provides better balance:")
                if time_diff > 0:
                    print(f"- Saves {time_diff} minutes for ${cost_diff:.2f} more (${(cost_diff/time_diff):.2f}/minute saved)")
                else:
                    print(f"- Costs ${abs(cost_diff):.2f} less but takes {abs(time_diff)} more minutes")
                if balanced_option["outbound"]["flight"]["Destination"] != balanced_option["return"]["flight"]["Origin"]:
                    print("- Uses different airports to optimize journey times")
                print_journey_summary(balanced_option, source_city, destination_city)
        else:
            print("\n⚖️ Balance Analysis:")
            if preferred_option["outbound"]["flight"]["Destination"] == preferred_option["return"]["flight"]["Origin"]:
                print("Your cheapest option is well-balanced because:")
                print("- It uses the same airport for departure and return, reducing ground transport complexity")
            else:
                print("Your cheapest option is well-balanced because:")
                print("- It optimizes both flight and ground transport times")
            
            flight_time = (preferred_option["outbound"]["flight"]["Flight Duration (mins)"] + 
                         preferred_option["return"]["flight"]["Flight Duration (mins)"])
            ground_time = preferred_option["total_time"] - flight_time
            ground_ratio = ground_time / preferred_option["total_time"]
            
            if ground_ratio <= 0.4:
                print("- Ground transport time is reasonable (less than 40% of total journey)")
            if flight_time <= min(opt["outbound"]["flight"]["Flight Duration (mins)"] + 
                                opt["return"]["flight"]["Flight Duration (mins)"] 
                                for opt in all_combinations) * 1.2:
                print("- Flight times are among the most efficient available")

def print_journey_summary(option, source_city, destination_city):
    """Helper function to print journey summary"""
    print(f"Outbound:")
    print(f"1. {source_city} → {option['outbound']['flight']['Origin']} Airport")
    print(f"   ({option['outbound']['ground_to_airport']['recommended_mode']}, "
          f"{option['outbound']['ground_to_airport']['duration_mins']} mins, "
          f"${option['outbound']['ground_to_airport']['cost_usd']}")
    print(f"   Note: {option['outbound']['ground_to_airport']['notes']}")
    
    print(f"2. Flight: {option['outbound']['flight']['Origin']} → "
          f"{option['outbound']['flight']['Destination']}")
    print(f"   ({option['outbound']['flight']['Airline']}, "
          f"{option['outbound']['flight']['Flight Duration (mins)']} mins, "
          f"{option['outbound']['flight']['Price']})")
    print(f"   Departure: {option['outbound']['flight']['Departure']}")
    print(f"   Arrival: {option['outbound']['flight']['Arrival']}")
    
    print(f"3. {option['outbound']['flight']['Destination']} Airport → {destination_city}")
    print(f"   ({option['outbound']['ground_from_airport']['recommended_mode']}, "
          f"{option['outbound']['ground_from_airport']['duration_mins']} mins, "
          f"${option['outbound']['ground_from_airport']['cost_usd']}")
    print(f"   Note: {option['outbound']['ground_from_airport']['notes']}")

    print(f"\nReturn:")
    print(f"1. {destination_city} → {option['return']['flight']['Origin']} Airport")
    print(f"   ({option['return']['ground_to_airport']['recommended_mode']}, "
          f"{option['return']['ground_to_airport']['duration_mins']} mins, "
          f"${option['return']['ground_to_airport']['cost_usd']}")
    print(f"   Note: {option['return']['ground_to_airport']['notes']}")
    
    print(f"2. Flight: {option['return']['flight']['Origin']} → "
          f"{option['return']['flight']['Destination']}")
    print(f"   ({option['return']['flight']['Airline']}, "
          f"{option['return']['flight']['Flight Duration (mins)']} mins, "
          f"{option['return']['flight']['Price']})")
    print(f"   Departure: {option['return']['flight']['Departure']}")
    print(f"   Arrival: {option['return']['flight']['Arrival']}")
    
    print(f"3. {option['return']['flight']['Destination']} Airport → {source_city}")
    print(f"   ({option['return']['ground_from_airport']['recommended_mode']}, "
          f"{option['return']['ground_from_airport']['duration_mins']} mins, "
          f"${option['return']['ground_from_airport']['cost_usd']}")
    print(f"   Note: {option['return']['ground_from_airport']['notes']}")

    print(f"\n💵 Total Cost: ${option['total_cost']:.2f}")
    print(f"⏱️ Total Time: {option['total_time']} minutes")
    print(f"🚗 Ground Transport Time: {option['total_time'] - (option['outbound']['flight']['Flight Duration (mins)'] + option['return']['flight']['Flight Duration (mins)'])} minutes")
    print(f"✈️ Flight Time: {option['outbound']['flight']['Flight Duration (mins)'] + option['return']['flight']['Flight Duration (mins)']} minutes")

if __name__ == "__main__":
    main()


