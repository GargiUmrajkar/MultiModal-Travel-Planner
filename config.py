import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
RAPIDAPI_HOST = os.getenv('RAPIDAPI_HOST', 'sky-scanner3.p.rapidapi.com')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# API Configuration
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_PERIOD = 60  # in seconds

# Error Messages
ERROR_MESSAGES = {
    'api_key_invalid': '❌ API Key is invalid or expired. Please check your RapidAPI subscription.',
    'timeout': '❌ API Request timed out. The server took too long to respond.',
    'connection_error': '❌ Connection error. Please check your internet connection.',
    'empty_response': '❌ API returned empty response',
    'no_flights': '⚠️ No valid flight data found for the specified route'
} 