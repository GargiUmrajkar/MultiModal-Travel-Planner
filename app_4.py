from openai import OpenAI
import json
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Literal, List, Dict, Optional
import time
import re
import os
from dotenv import load_dotenv

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

def format_date(year, month):
    """ Helper function to format date in 'Month Year' format """
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    return f"{month_names[int(month) - 1]} {year}"

def select_location(driver, wait, input_selector, location):
    """ Selects a location and confirms selection properly """
    location_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, input_selector)))
    location_input.click()
    location_input.clear()
    location_input.send_keys(location)
    time.sleep(2)

    try:
        location_input.send_keys(Keys.ARROW_DOWN)
        location_input.send_keys(Keys.ENTER)
    except:
        print(f"Could not find a suggestion for {location}, trying ENTER key")
        location_input.send_keys(Keys.ENTER)

    time.sleep(1)
    if location_input.get_attribute("value").strip() == "":
        raise Exception(f"Failed to select {location}. The field is still empty.")

def load_all_results(driver, wait):
    """ Clicks 'See More' until no more results are available. """
    print("Loading all results...")
    while True:
        try:
            time.sleep(2)
            see_more_button = wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//*[contains(@class, 'C9btmpKqYElu') and contains(@class, 'hWqODJW5oS5g') and contains(@class, 'kxQTKJCuApMn') and contains(@class, 'ydCZ8Dnno8TR')]"
            )))
            
            print(f"Button text: {see_more_button.text}")
            print(f"Button displayed: {see_more_button.is_displayed()}")
            print(f"Button enabled: {see_more_button.is_enabled()}")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", see_more_button)
            time.sleep(2)
            
            driver.execute_script("""
                var element = arguments[0];
                var rect = element.getBoundingClientRect();
                var eventInitDict = {
                    clientX: rect.left + rect.width/2,
                    clientY: rect.top + rect.height/2,
                    bubbles: true,
                    cancelable: true,
                    view: window
                };
                element.dispatchEvent(new MouseEvent('mouseover', eventInitDict));
            """, see_more_button)
            time.sleep(1)

            possible_texts = ["See more", "Show more", "Load more", "More results"]
            button_text = see_more_button.text.lower()
            
            if see_more_button.is_displayed() and any(text.lower() in button_text for text in possible_texts):
                print(f"Found clickable button with text: {see_more_button.text}")
                try:
                    see_more_button.click()
                except:
                    try:
                        driver.execute_script("arguments[0].click();", see_more_button)
                    except:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(driver)
                        actions.move_to_element(see_more_button).click().perform()
                
                print("Successfully clicked the button")
                time.sleep(2)
            else:
                print(f"Button found but not clickable. Text: '{see_more_button.text}'")
                print("Checking if we've reached the end of results...")
                
                end_markers = ["No more results", "End of results", "That's all"]
                if any(marker.lower() in button_text for marker in end_markers):
                    print("Reached end of results")
                    break
                    
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(1)

        except Exception as e:
            print(f"No more 'See More' button found or error occurred: {e}")
            break

    print("Finished loading all results")

def scrape_results(driver, wait):
    """ Extract travel options from the search results page """
    try:
        print("Starting to scrape results...")
        time.sleep(5)
        
        results_container = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//*[contains(@class, 'X9dnSAz3W7v8')]"
        )))
        print("Found results container")
        
        results = results_container.find_elements(
            By.XPATH,
            ".//*[contains(@class, 'gPwYYvClbIG4')]"
        )
        print(f"Found {len(results)} trip elements")
        
        if not results:
            print("No travel options found.")
            return []

        travel_options = []
        for idx, result in enumerate(results):
            try:
                # print(f"\nProcessing trip {idx + 1}:")
                driver.execute_script("arguments[0].scrollIntoView(true);", result)
                time.sleep(1)

                # print(f"Trip HTML: {result.get_attribute('outerHTML')}")

                # Extract provider
                try:
                    provider = None
                    print("\nAttempting to find provider...")
                    
                    try:
                        provider_element = result.find_element(
                            By.XPATH,
                            ".//div[contains(@class, 'oiE0BtFyaVer')]"
                        )
                        provider = provider_element.text.strip()
                        print(f"Method 1 - Found provider: {provider}")
                    except Exception as e:
                        print(f"Method 1 failed: {str(e)}")

                    if not provider:
                        try:
                            provider_container = result.find_element(
                                By.XPATH,
                                ".//div[contains(@class, 'jW2iTFL2ieRa')]"
                            )
                            provider_element = provider_container.find_element(
                                By.XPATH,
                                ".//div[contains(@class, '_2nswdy5H41iJ')]"
                            )
                            provider = provider_element.text.strip()
                            print(f"Method 2 - Found provider: {provider}")
                        except Exception as e:
                            print(f"Method 2 failed: {str(e)}")

                    if not provider:
                        try:
                            anchor = result.find_element(
                                By.XPATH,
                                ".//a[contains(@class, 'XsXxhvVWETRD')]"
                            )
                            print("Found anchor element")
                            
                            img_element = anchor.find_element(
                                By.XPATH,
                                ".//img[contains(@class, '-fTaxk6VaeXP')]"
                            )
                            provider = img_element.get_attribute('alt')
                            print(f"Method 3 - Found provider from img alt: {provider}")
                            
                            if not provider:
                                provider = img_element.get_attribute('title')
                                print(f"Method 3 (fallback) - Found provider from img title: {provider}")
                                
                        except Exception as e:
                            print(f"Method 3 failed: {str(e)}")
                            print("Full HTML structure:")
                            print(result.get_attribute('outerHTML'))

                    if provider:
                        provider = provider.strip()
                        print(f"Final provider found: {provider}")
                    else:
                        raise Exception("Could not find provider with any known method")
                except Exception as e:
                    print(f"All provider extraction methods failed: {e}")
                    provider = "N/A"

                # Extract times
                try:
                    time_elements = result.find_elements(
                        By.XPATH,
                        ".//div[contains(@class, 'qxJ8gvqPakat')]"
                    )
                    departure_time = time_elements[0].text.strip() if len(time_elements) > 0 else "N/A"
                    print(f"Found departure time: {departure_time}")
                    
                    arrival_element = time_elements[1] if len(time_elements) > 1 else None
                    if arrival_element:
                        arrival_time = arrival_element.text.strip()
                        next_day_span = arrival_element.find_elements(
                            By.XPATH,
                            ".//span[contains(@class, 'jsI1jjww+3nz')]"
                        )
                        if next_day_span:
                            arrival_time += f" ({next_day_span[0].text})"
                        print(f"Found arrival time: {arrival_time}")
                    else:
                        arrival_time = "N/A"
                except Exception as e:
                    print(f"Error finding times: {e}")
                    departure_time = "N/A"
                    arrival_time = "N/A"

                # Extract price
                price = "N/A"
                price_classes = ['_22OZINQvyonV', 'price', 'fare']
                for class_name in price_classes:
                    try:
                        price_element = result.find_element(
                            By.XPATH,
                            f".//div[contains(@class, '{class_name}')]"
                        )
                        price = price_element.text.strip()
                        print(f"Found price with class {class_name}: {price}")
                        break
                    except:
                        continue

                if price == "N/A":
                    try:
                        price_elements = result.find_elements(By.XPATH, ".//*[contains(text(), '$')]")
                        if price_elements:
                            price = price_elements[0].text.strip()
                            print(f"Found price by $ sign: {price}")
                    except Exception as e:
                        print(f"Error finding price by $ sign: {e}")

                travel_options.append({
                    'provider': provider,
                    'departure_time': departure_time,
                    'arrival_time': arrival_time,
                    'price': price
                })
                print(f"Successfully extracted trip: {provider} - {departure_time} to {arrival_time} - {price}")
                
            except Exception as e:
                print(f"Error extracting trip details: {e}")
                continue

        return travel_options

    except Exception as e:
        print(f"Error during scraping: {e}")
        return []

def sort_results(driver, wait, sort_method: Literal["Wanderlist", "Cheapest", "Fastest", "Earliest", "Latest"] = "Wanderlist"):
    """Sort the results based on the specified method"""
    print(f"\nAttempting to sort results by: {sort_method}")
    try:
        dropdown_button = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@aria-label='Sort' and contains(@class, 'hvFXI4LQhqZ6') and contains(@class, 'Fdjz4+kRXksx')]"
        )))
        
        print("Found sort dropdown button")
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_button)
        time.sleep(1)
        
        try:
            print("Attempting to click sort dropdown...")
            dropdown_button.click()
        except Exception as click_error:
            print(f"Direct click failed: {click_error}")
            try:
                print("Trying JavaScript click...")
                driver.execute_script("arguments[0].click();", dropdown_button)
            except Exception as js_error:
                print(f"JavaScript click failed: {js_error}")
                try:
                    print("Trying ActionChains click...")
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(driver)
                    actions.move_to_element(dropdown_button).click().perform()
                except Exception as action_error:
                    print(f"ActionChains click failed: {action_error}")
                    raise Exception("All click methods failed for dropdown")

        print("Successfully clicked sort dropdown")
        time.sleep(1)
        
        sort_option = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            f"//span[@class='GxsKRvLipFnO' and @data-id='sortOption' and text()='{sort_method}']"
        )))
        
        print(f"Found sort option for {sort_method}")
        
        try:
            print(f"Attempting to click {sort_method} option...")
            sort_option.click()
        except Exception as click_error:
            print(f"Direct click failed: {click_error}")
            try:
                print("Trying JavaScript click...")
                driver.execute_script("arguments[0].click();", sort_option)
            except Exception as js_error:
                print(f"JavaScript click failed: {js_error}")
                try:
                    print("Trying ActionChains click...")
                    actions = ActionChains(driver)
                    actions.move_to_element(sort_option).click().perform()
                except Exception as action_error:
                    print(f"ActionChains click failed: {action_error}")
                    raise Exception("All click methods failed for sort option")
        
        print(f"Successfully selected sort option: {sort_method}")
        time.sleep(3)
        
    except Exception as e:
        print(f"Error during sorting: {e}")
        print("HTML structure of the area:")
        try:
            sort_area = driver.find_element(By.CLASS_NAME, "hvFXI4LQhqZ6")
            print(sort_area.get_attribute('outerHTML'))
        except:
            print("Could not find sort area for debugging")

def get_bus_options_wanderu(from_location: str, to_location: str, travel_date: str, 
                          preferred_time: Optional[str] = None, 
                          optimize_for: str = "cost") -> List[Dict]:
    """
    Get bus options from Wanderu with smart sorting based on optimization preference
    """
    # Clean up city names - remove any airport codes and get proper city names
    def clean_city_name(location: str) -> str:
        """
        Clean up location name to get proper city name
        - Handles airport codes (e.g., ORD -> Chicago)
        - Removes airport/international/regional suffixes
        - Removes state/country information
        """
        # First check if it's an airport code
        if re.match(r'^[A-Z]{3}$', location):
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user", 
                    "content": f"What city is the airport code {location} in? Just respond with the city name only."
                }]
            )
            return response.choices[0].message.content.strip().split(',')[0]

        # If location contains "Airport", extract the city name
        if "Airport" in location:
            # First try to extract any airport code
            airport_code_match = re.search(r'\(([A-Z]{3})\)', location)
            if airport_code_match:
                code = airport_code_match.group(1)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{
                        "role": "user", 
                        "content": f"What city is the airport code {code} in? Just respond with the city name only."
                    }]
                )
                return response.choices[0].message.content.strip().split(',')[0]
            
            # If no airport code, get the text before "Airport"
            city = location.split("Airport")[0].strip()
            # Remove any parentheses and their contents
            city = re.sub(r'\([^)]*\)', '', city).strip()
            # Remove common airport prefixes/suffixes
            city = re.sub(r'(?i)(international|regional|municipal)', '', city).strip()
            return city

        # For non-airport locations, just take the city part
        # Remove any parentheses and their contents first
        city = re.sub(r'\([^)]*\)', '', location).strip()
        # Then split on comma and take first part
        return city.split(',')[0].strip()

    from_city = clean_city_name(from_location)
    to_city = clean_city_name(to_location)
    print(f"\n🔍 Searching for bus options from {from_city} to {to_city}")

    driver = webdriver.Chrome()
    try:
        driver.get("https://www.wanderu.com/")
        wait = WebDriverWait(driver, 20)

        # Handle hotel checkbox
        try:
            hotel_label = wait.until(EC.presence_of_element_located((
                By.XPATH,
                '//label[contains(@class, "yiYfW3X2gl4h") and contains(@class, "VMJ3+cpdgtQz")]'
            )))
            checkbox = hotel_label.find_element(By.CLASS_NAME, "Z73opDNuOcq9")
            if checkbox.is_selected():
                hotel_label.click()
                time.sleep(1)
        except Exception as e:
            print(f"Note: Could not handle hotel checkbox: {e}")

        # Select locations
        select_location(driver, wait, 'input[placeholder="From: address or city"]', from_city)
        select_location(driver, wait, 'input[placeholder="To: address or city"]', to_city)

        # Set date using calendar widget
        try:
            print("Setting travel date...")
            # Find and click the date picker input
            date_picker = wait.until(EC.element_to_be_clickable((
                By.CLASS_NAME, 'departDatePicker'
            )))
            
            # Scroll into view and click
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_picker)
            time.sleep(1)
            
            try:
                date_picker.click()
            except:
                driver.execute_script("arguments[0].click();", date_picker)
            
            time.sleep(1)

            year, month, day = travel_date.split('-')
            desired_month_year = format_date(year, month)

            # Navigate to correct month/year using the working selectors
            max_attempts = 12
            attempts = 0
            while attempts < max_attempts:
                current_month_year = wait.until(EC.visibility_of_element_located((
                    By.CSS_SELECTOR, 'span[data-id="header-date"]'
                ))).text
                
                if current_month_year == desired_month_year:
                    break
                    
                next_month_button = wait.until(EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 'button[aria-label="next-month"]'
                )))
                next_month_button.click()
                time.sleep(1)
                attempts += 1
            
            # Click the specific day using the working selector
            day_element = wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, f'td[aria-label="{day}-active"]'
            )))
            
            try:
                day_element.click()
            except:
                driver.execute_script("arguments[0].click();", day_element)
            
            time.sleep(2)
            print(f"Successfully set date to {travel_date}")
        except Exception as e:
            print(f"Error setting date: {e}")
            raise

        # Search
        try:
            search_button = wait.until(EC.element_to_be_clickable((
                By.XPATH, '//button[contains(@label, "Search")]'
            )))
            search_button.click()
            time.sleep(5)
            print("Successfully clicked search button")
        except Exception as e:
            print(f"Error clicking search button: {e}")
            raise

        # Smart sorting based on optimization preference and timing
        def try_sort_and_get_results(sort_method: str) -> List[Dict]:
            sort_results(driver, wait, sort_method)
            results = scrape_results(driver, wait)
            if preferred_time and results:
                preferred_dt = parse_time(preferred_time)
                if preferred_dt:
                    # Add 1 hour grace period
                    preferred_dt = preferred_dt.replace(hour=preferred_dt.hour + 1)
                    filtered = []
                    for option in results:
                        departure_dt = parse_time(option['departure_time'])
                        if departure_dt and departure_dt >= preferred_dt:
                            filtered.append(option)
                    return filtered
            return results

        # Try different sort methods based on optimization preference
        if optimize_for == "cost":
            # First try cheapest
            results = try_sort_and_get_results("Cheapest")
            if results:
                return results[:10]  # Return first 10 cheapest options that match timing
            
            # If no matches, check if we need earlier or later options
            if preferred_time:
                preferred_dt = parse_time(preferred_time)
                if preferred_dt:
                    # Try Latest if we need later options
                    results = try_sort_and_get_results("Latest")
                    if not results:
                        # Try Earliest if we need earlier options
                        results = try_sort_and_get_results("Earliest")
                    if not results:
                        # Last resort, try Fastest
                        results = try_sort_and_get_results("Fastest")
            
        else:  # optimize_for == "time"
            # First try fastest
            results = try_sort_and_get_results("Fastest")
            if results:
                return results[:10]  # Return first 10 fastest options that match timing
            
            # If no matches, try Latest/Earliest based on preferred time
            if preferred_time:
                preferred_dt = parse_time(preferred_time)
                if preferred_dt:
                    # Try Latest if we need later options
                    results = try_sort_and_get_results("Latest")
                    if not results:
                        # Try Earliest if we need earlier options
                        results = try_sort_and_get_results("Earliest")

        return results if results else []

    finally:
        driver.quit()

def parse_time(time_str: str) -> datetime:
    """Convert time string to datetime object"""
    try:
        return datetime.strptime(time_str, "%H:%M")
    except ValueError:
        return None

def get_ground_transit_details(from_location: str, to_location: str, travel_date: str, 
                              preferred_time: Optional[str] = None) -> Dict:
    """
    Get ground transportation details based on distance and available options
    """
    try:
        # Check if this is an airport route
        from_is_airport = "Airport" in from_location
        to_is_airport = "Airport" in to_location
        
        # If neither location is an airport, use cab
        if not from_is_airport and not to_is_airport:
            return {
                "duration_mins": 30,
                "cost_usd": 25,
                "recommended_mode": "cab",
                "notes": "Direct cab service available"
            }
        
        # Extract city names and clean them
        def clean_city_name(location: str) -> str:
            # If it's an airport location, extract the city name
            if "Airport" in location:
                # Try to extract airport code first
                code_match = re.search(r'\(([A-Z]{3})\)', location)
                if code_match:
                    code = code_match.group(1)
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{
                            "role": "user", 
                            "content": f"What city is the airport code {code} in? Just respond with the city name only."
                        }]
                    )
                    return response.choices[0].message.content.strip().split(',')[0]
                
                # If no code, get text before "Airport"
                city = location.split("Airport")[0].strip()
                city = re.sub(r'\([^)]*\)', '', city).strip()
                city = re.sub(r'(?i)(international|regional|municipal)', '', city).strip()
                return city
            
            # For non-airport locations, just take the city part
            city = re.sub(r'\([^)]*\)', '', location).strip()
            return city.split(',')[0].strip()

        from_city = clean_city_name(from_location)
        to_city = clean_city_name(to_location)
        
        # If cities are the same, use cab
        if from_city.lower() == to_city.lower():
            print(f"\nℹ️ Same city detected ({from_city}), using cab service")
            return {
                "duration_mins": 30,
                "cost_usd": 25,
                "recommended_mode": "cab",
                "notes": "Same city, using cab service"
            }
            
        # Check if destination city has a major airport
        has_major_airport = False
        if from_is_airport:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user", 
                    "content": f"Does {to_city} have a major airport? Just respond with yes or no."
                }]
            )
            has_major_airport = "yes" in response.choices[0].message.content.lower()
        else:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user", 
                    "content": f"Does {from_city} have a major airport? Just respond with yes or no."
                }]
            )
            has_major_airport = "yes" in response.choices[0].message.content.lower()
        
        # If city has a major airport, use cab
        if has_major_airport:
            print(f"\nℹ️ City has major airport ({from_city if from_is_airport else to_city}), using cab service")
            return {
                "duration_mins": 45,
                "cost_usd": 35,
                "recommended_mode": "cab",
                "notes": "City has major airport, using cab service"
            }
        
        # Only search for bus options if we haven't returned cab service yet
        print(f"\n🔍 Checking bus options from {from_city} to {to_city}")
        
        try:
            # For longer distances, try to find bus options
            # Only try one sort method based on whether we have a preferred time
            if preferred_time:
                # If we have a preferred time, try "Latest" first to find options after that time
                options = get_bus_options_wanderu(from_city, to_city, travel_date, 
                                                preferred_time=preferred_time,
                                                optimize_for="time")  # Use time optimization to find suitable departure times
            else:
                # If no preferred time, just get cheapest options
                options = get_bus_options_wanderu(from_city, to_city, travel_date, 
                                                optimize_for="cost")
            
            if options:
                best_option = options[0]  # Take the first matching option
                try:
                    # Calculate duration in minutes between departure and arrival times
                    duration = 0
                    if best_option['departure_time'] != "N/A" and best_option['arrival_time'] != "N/A":
                        # Extract times from the time strings
                        departure_match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)', best_option['departure_time'])
                        arrival_match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)', best_option['arrival_time'])
                        
                        if departure_match and arrival_match:
                            # Convert to 24-hour format
                            def to_24hr(hour, minute, meridiem):
                                hour = int(hour)
                                if meridiem == 'PM' and hour != 12:
                                    hour += 12
                                elif meridiem == 'AM' and hour == 12:
                                    hour = 0
                                return datetime.strptime(f"{hour:02d}:{minute}", "%H:%M")

                            dep_time = to_24hr(
                                departure_match.group(1),
                                departure_match.group(2),
                                departure_match.group(3)
                            )
                            arr_time = to_24hr(
                                arrival_match.group(1),
                                arrival_match.group(2),
                                arrival_match.group(3)
                            )
                            
                            # Handle case where arrival is next day
                            if '(+1)' in best_option['arrival_time']:
                                arr_time = arr_time + timedelta(days=1)
                            
                            # Calculate duration in minutes
                            duration = int((arr_time - dep_time).total_seconds() / 60)
                            if duration < 0:  # If negative, arrival must be next day
                                duration += 24 * 60
                    
                    price = float(best_option['price'].replace('$', '').replace(',', ''))
                    
                    return {
                        "duration_mins": duration,
                        "cost_usd": price,
                        "recommended_mode": "bus",
                        "notes": f"Service by {best_option['provider']}",
                        "departure_time": best_option['departure_time'],
                        "arrival_time": best_option['arrival_time']
                    }
                except Exception as e:
                    print(f"Error processing bus option: {e}")
                    pass
        except Exception as e:
            print(f"Error searching for bus options: {e}")
        
        # If no suitable bus options found or error occurred, use cab with distance-based estimate
        print("ℹ️ Using cab service for this route")
        
        # Use OpenAI to estimate the distance and travel time
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user", 
                "content": f"What is the approximate driving distance in miles and typical driving time in minutes from {from_city} to {to_city}? Just respond with two numbers separated by a comma: distance,minutes"
            }]
        )
        try:
            distance, minutes = map(float, response.choices[0].message.content.strip().split(','))
            # Estimate cab fare: $3 base + $2.50 per mile
            estimated_fare = 3 + (2.50 * distance)
            return {
                "duration_mins": int(minutes),
                "cost_usd": round(estimated_fare, 2),
                "recommended_mode": "cab",
                "notes": f"Using cab service for {distance:.1f} mile journey"
            }
        except:
            # If estimation fails, use default values
            return {
                "duration_mins": 60,
                "cost_usd": 45,
                "recommended_mode": "cab",
                "notes": "Using cab service for this route"
            }
    except Exception as e:
        print(f"Error in get_ground_transit_details: {e}")
        # Return safe default values
        return {
            "duration_mins": 60,
            "cost_usd": 45,
            "recommended_mode": "cab",
            "notes": "Using default cab service due to error"
        }

def find_matching_ground_transport(flight_arrival_time: str, from_location: str, to_location: str, 
                                 travel_date: str, optimize_for: str) -> Optional[Dict]:
    """
    Find matching ground transport options based on flight arrival time and optimization preference
    """
    # Clean up location names
    from_city = from_location.split()[0].lower()  # Take only the city name
    to_city = to_location.split()[0].lower()  # Take only the city name
    
    # If same city, return None as we'll use cab
    if from_city == to_city:
        print(f"\nℹ️ Same city detected ({from_city}), skipping bus search")
        return None
    
    # Check if destination has a major airport
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{
            "role": "user", 
            "content": f"Does {to_city} have a major airport? Just respond with yes or no."
        }]
    )
    if "yes" in response.choices[0].message.content.lower():
        print(f"\nℹ️ Destination has major airport, skipping bus search")
        return None
    
    # Try only one sort method based on optimization preference
    sort_method = "Fastest" if optimize_for == "time" else "Cheapest"
    
    try:
        options = get_bus_options_wanderu(from_location, to_location, travel_date, 
                                        flight_arrival_time, sort_method)
        if options:
            return options[0]  # Return the first matching option
    except Exception as e:
        print(f"Error searching for bus options: {e}")
    
    return None  # Return None if no options found or if search fails

# Import all functions from app_3.py
from app_3 import (
    get_major_airports,
    search_flights,
    extract_flight_details,
    get_best_balanced_option,
    print_journey_summary
)

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
    budget = float('inf')
    if preference == "cost":
        budget = float(input("Enter your maximum budget: "))

    # Get airports for both cities
    print("\n🔍 Finding major airports...")
    source_airports = get_major_airports(source_city)
    destination_airports = get_major_airports(destination_city)

    if not source_airports or not destination_airports:
        print("❌ No valid airports found for source or destination. Try again.")
        return

    print(f"\n✈️ Found airports:")
    print(f"Source: {', '.join(source_airports)}")
    print(f"Destination: {', '.join(destination_airports)}")

    print("\n🔄 Analyzing all possible combinations...")
    all_combinations = []
    
    # Cache for flight searches and ground transit details
    flight_cache = {}
    transit_cache = {}

    def get_cached_flight(from_airport, to_airport, date, max_retries=3):
        """Get flight details with caching and retries"""
        cache_key = f"{from_airport}-{to_airport}-{date}"
        if cache_key not in flight_cache:
            for attempt in range(max_retries):
                try:
                    print(f"\n🔍 Searching flights from {from_airport} to {to_airport} on {date} (Attempt {attempt + 1}/{max_retries})")
                    flight_cache[cache_key] = search_flights(
                        "https://sky-scanner3.p.rapidapi.com/flights/search-one-way",
                        {"fromEntityId": from_airport, "toEntityId": to_airport, "departDate": date}
                    )
                    if flight_cache[cache_key]:
                        break
                    print(f"❌ No flights found from {from_airport} to {to_airport} on {date}")
                except Exception as e:
                    print(f"❌ Error searching flights (Attempt {attempt + 1}): {str(e)}")
                    if attempt < max_retries - 1:
                        print("Retrying in 5 seconds...")
                        time.sleep(5)
                    else:
                        print("Max retries reached. Moving to next option.")
                        flight_cache[cache_key] = None
        return flight_cache[cache_key]

    def get_cached_transit(from_loc, to_loc, date, preferred_time=None):
        """Get ground transit details with caching"""
        cache_key = f"{from_loc}-{to_loc}-{date}-{preferred_time}"
        if cache_key not in transit_cache:
            transit_cache[cache_key] = get_ground_transit_details(from_loc, to_loc, date, preferred_time)
        return transit_cache[cache_key]

    # Find all valid combinations
    for src_airport in source_airports:
        source_to_airport = get_cached_transit(source_city, f"{src_airport} Airport", depart_date)
        
        for dest_airport_in in destination_airports:
            flight_to = get_cached_flight(src_airport, dest_airport_in, depart_date)
            if not flight_to:
                continue
                
            outbound_flight = extract_flight_details(flight_to)
            if not outbound_flight:
                continue
                
            # Get ground transport details after flight arrival
            airport_to_dest = get_cached_transit(
                f"{dest_airport_in} Airport", 
                destination_city, 
                depart_date,
                outbound_flight["Arrival"]
            )
            
            for dest_airport_out in destination_airports:
                dest_to_airport = get_cached_transit(destination_city, f"{dest_airport_out} Airport", return_date)
                
                flight_back = get_cached_flight(dest_airport_out, src_airport, return_date)
                if not flight_back:
                    continue
                
                return_flight = extract_flight_details(flight_back)
                if not return_flight:
                    continue
                
                # Get ground transport details after flight arrival
                airport_to_source = get_cached_transit(
                    f"{src_airport} Airport", 
                    source_city, 
                    return_date,
                    return_flight["Arrival"]
                )
                
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

    # Get preferred option based on user's choice
    if preference == "cost":
        preferred_option = min(all_combinations, key=lambda x: x["total_cost"])
        print("\n💰 Best Option by Cost (Your Preference):")
    else:
        preferred_option = min(all_combinations, 
            key=lambda x: (x["outbound"]["flight"]["Flight Duration (mins)"] + 
                         x["return"]["flight"]["Flight Duration (mins)"])
        )
        print("\n⚡ Best Option by Time (Your Preference):")

    # Print preferred option summary
    print("\n📋 Your Preferred Journey Summary:")
    print_journey_summary(preferred_option, source_city, destination_city)

    # Find matching bus/train options for ground transport
    print("\n🔍 Searching for matching ground transport options...")
    
    # For outbound journey
    outbound_arrival = preferred_option["outbound"]["flight"]["Arrival"]
    matching_outbound = find_matching_ground_transport(
        outbound_arrival,
        preferred_option["outbound"]["flight"]["Destination"],
        destination_city,
        depart_date,
        preference
    )
    if matching_outbound:
        print("\n🚌 Available Bus/Train Options for Outbound:")
        print(f"Provider: {matching_outbound['provider']}")
        print(f"Departure: {matching_outbound['departure_time']}")
        print(f"Arrival: {matching_outbound['arrival_time']}")
        print(f"Price: {matching_outbound['price']}")

    # For return journey
    return_arrival = preferred_option["return"]["flight"]["Arrival"]
    matching_return = find_matching_ground_transport(
        return_arrival,
        preferred_option["return"]["flight"]["Destination"],
        source_city,
        return_date,
        preference
    )
    if matching_return:
        print("\n🚌 Available Bus/Train Options for Return:")
        print(f"Provider: {matching_return['provider']}")
        print(f"Departure: {matching_return['departure_time']}")
        print(f"Arrival: {matching_return['arrival_time']}")
        print(f"Price: {matching_return['price']}")

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
            
            if other_flight_times:
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
    """Print a detailed summary of the journey including ground transport details"""
    print("\nOutbound:")
    # Source to airport
    ground_to = option["outbound"]["ground_to_airport"]
    print(f"1. {source_city} → {option['outbound']['flight']['Origin']} Airport")
    print(f"   ({ground_to['recommended_mode']}, {ground_to['duration_mins']} mins, ${ground_to['cost_usd']})")
    print(f"   Note: {ground_to['notes']}")
    if ground_to['recommended_mode'] == 'bus' and 'departure_time' in ground_to:
        print(f"   Departure: {ground_to['departure_time']}")
        print(f"   Arrival: {ground_to['arrival_time']}")

    # Flight details
    outbound = option["outbound"]["flight"]
    print(f"2. Flight: {outbound['Origin']} → {outbound['Destination']}")
    print(f"   ({outbound['Airline']}, {outbound['Flight Duration (mins)']} mins, ${outbound['Price']})")
    print(f"   Departure: {outbound['Departure']}")
    print(f"   Arrival: {outbound['Arrival']}")

    # Airport to destination
    ground_from = option["outbound"]["ground_from_airport"]
    print(f"3. {outbound['Destination']} Airport → {destination_city}")
    print(f"   ({ground_from['recommended_mode']}, {ground_from['duration_mins']} mins, ${ground_from['cost_usd']})")
    print(f"   Note: {ground_from['notes']}")
    if ground_from['recommended_mode'] == 'bus' and 'departure_time' in ground_from:
        print(f"   Departure: {ground_from['departure_time']}")
        print(f"   Arrival: {ground_from['arrival_time']}")

    print("\nReturn:")
    # Destination to airport
    ground_to = option["return"]["ground_to_airport"]
    print(f"1. {destination_city} → {option['return']['flight']['Origin']} Airport")
    print(f"   ({ground_to['recommended_mode']}, {ground_to['duration_mins']} mins, ${ground_to['cost_usd']})")
    print(f"   Note: {ground_to['notes']}")
    if ground_to['recommended_mode'] == 'bus' and 'departure_time' in ground_to:
        print(f"   Departure: {ground_to['departure_time']}")
        print(f"   Arrival: {ground_to['arrival_time']}")

    # Return flight details
    return_flight = option["return"]["flight"]
    print(f"2. Flight: {return_flight['Origin']} → {return_flight['Destination']}")
    print(f"   ({return_flight['Airline']}, {return_flight['Flight Duration (mins)']} mins, ${return_flight['Price']})")
    print(f"   Departure: {return_flight['Departure']}")
    print(f"   Arrival: {return_flight['Arrival']}")

    # Airport to source
    ground_from = option["return"]["ground_from_airport"]
    print(f"3. {return_flight['Destination']} Airport → {source_city}")
    print(f"   ({ground_from['recommended_mode']}, {ground_from['duration_mins']} mins, ${ground_from['cost_usd']})")
    print(f"   Note: {ground_from['notes']}")
    if ground_from['recommended_mode'] == 'bus' and 'departure_time' in ground_from:
        print(f"   Departure: {ground_from['departure_time']}")
        print(f"   Arrival: {ground_from['arrival_time']}")

    print(f"\n💵 Total Cost: ${option['total_cost']:.2f}")
    print(f"⏱️ Total Time: {option['total_time']} minutes")
    print(f"🚗 Ground Transport Time: {option['outbound']['ground_to_airport']['duration_mins'] + option['outbound']['ground_from_airport']['duration_mins'] + option['return']['ground_to_airport']['duration_mins'] + option['return']['ground_from_airport']['duration_mins']} minutes")
    print(f"✈️ Flight Time: {option['outbound']['flight']['Flight Duration (mins)'] + option['return']['flight']['Flight Duration (mins)']} minutes")

if __name__ == "__main__":
    main()


