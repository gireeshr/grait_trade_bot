# env_utils.py
import os
from dotenv import load_dotenv

# Load .env once, on first import
load_dotenv()

def get_env_value(key: str) -> str:
    """
    Retrieve an environment variable (stored uppercase in .env).
    Raises KeyError if not found.
    """
    upper_key = key.upper()
    val = os.getenv(upper_key)
    if val is None:
        raise KeyError(f"Environment variable '{upper_key}' not found.")
    return val
