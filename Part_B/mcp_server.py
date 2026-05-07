"""
Part B Task 1: MCP Server Implementation
==========================================
A standalone Model Context Protocol (MCP) server that exposes
structured tools for a weather and currency conversion service.

This is an INDEPENDENT use-case, separate from Part A.
Demonstrates MCP design principles: Model, Context, Tools, Execution layer.
"""

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import json
import math
from datetime import datetime

# ─── Initialize MCP Server ──────────────────────────────────────────────────

mcp = FastMCP(
    name="WeatherCurrencyMCPServer",
)


# ─── Tool 1: Weather Forecast ───────────────────────────────────────────────

@mcp.tool()
def get_weather_forecast(city: str, days: int = 3) -> str:
    """Get the weather forecast for a city for the specified number of days.

    Args:
        city: Name of the city (e.g., 'Islamabad', 'Lahore', 'Karachi').
        days: Number of days to forecast (1-7). Defaults to 3.

    Returns:
        JSON string with daily forecasts including temperature, condition,
        humidity, and wind speed.
    """
    # Simulated weather data (deterministic based on city name for reproducibility)
    city_lower = city.lower().strip()
    seed = sum(ord(c) for c in city_lower)

    conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Thunderstorm", "Clear", "Windy"]
    base_temp = 20 + (seed % 15)  # Base temperature varies by city

    forecasts = []
    for day in range(min(days, 7)):
        day_seed = seed + day * 7
        temp_high = base_temp + (day_seed % 8)
        temp_low = temp_high - 5 - (day_seed % 5)
        condition = conditions[day_seed % len(conditions)]
        humidity = 40 + (day_seed % 40)
        wind_speed = 5 + (day_seed % 20)

        forecast_date = datetime.now().strftime("%Y-%m-%d")

        forecasts.append({
            "date": f"Day {day + 1}",
            "temperature_high_c": temp_high,
            "temperature_low_c": temp_low,
            "condition": condition,
            "humidity_pct": humidity,
            "wind_speed_kmh": wind_speed,
        })

    return json.dumps({
        "city": city,
        "country": "Pakistan",
        "forecast_days": len(forecasts),
        "generated_at": datetime.now().isoformat(),
        "forecasts": forecasts,
    }, indent=2)


# ─── Tool 2: Currency Conversion ────────────────────────────────────────────

@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert (must be positive).
        from_currency: Source currency code (e.g., 'USD', 'EUR', 'PKR', 'GBP').
        to_currency: Target currency code (e.g., 'USD', 'EUR', 'PKR', 'GBP').

    Returns:
        JSON string with conversion result including exchange rate,
        converted amount, and timestamp.
    """
    # Exchange rates relative to USD (simulated but realistic)
    rates_to_usd = {
        "USD": 1.0,
        "EUR": 0.92,
        "GBP": 0.79,
        "PKR": 278.50,
        "INR": 83.12,
        "CNY": 7.24,
        "JPY": 149.80,
        "AED": 3.67,
        "SAR": 3.75,
        "CAD": 1.36,
        "AUD": 1.53,
    }

    from_upper = from_currency.upper().strip()
    to_upper = to_currency.upper().strip()

    if from_upper not in rates_to_usd:
        return json.dumps({"error": f"Unsupported currency: {from_upper}. Supported: {list(rates_to_usd.keys())}"})
    if to_upper not in rates_to_usd:
        return json.dumps({"error": f"Unsupported currency: {to_upper}. Supported: {list(rates_to_usd.keys())}"})
    if amount <= 0:
        return json.dumps({"error": "Amount must be positive"})

    # Convert: from_currency → USD → to_currency
    amount_in_usd = amount / rates_to_usd[from_upper]
    converted_amount = amount_in_usd * rates_to_usd[to_upper]
    exchange_rate = rates_to_usd[to_upper] / rates_to_usd[from_upper]

    return json.dumps({
        "from_currency": from_upper,
        "to_currency": to_upper,
        "original_amount": amount,
        "converted_amount": round(converted_amount, 2),
        "exchange_rate": round(exchange_rate, 6),
        "timestamp": datetime.now().isoformat(),
    }, indent=2)


# ─── Tool 3: Distance Calculator ────────────────────────────────────────────

@mcp.tool()
def calculate_distance(city1: str, city2: str) -> str:
    """Calculate the approximate distance between two Pakistani cities.

    Args:
        city1: First city name (e.g., 'Islamabad', 'Karachi').
        city2: Second city name (e.g., 'Lahore', 'Peshawar').

    Returns:
        JSON string with distance in kilometers and estimated travel time.
    """
    # Coordinates of major Pakistani cities (lat, lon)
    cities = {
        "islamabad": (33.6844, 73.0479),
        "lahore": (31.5204, 74.3587),
        "karachi": (24.8607, 67.0011),
        "peshawar": (34.0151, 71.5249),
        "quetta": (30.1798, 66.9750),
        "faisalabad": (31.4504, 73.1350),
        "multan": (30.1575, 71.5249),
        "rawalpindi": (33.5651, 73.0169),
        "sialkot": (32.4945, 74.5229),
        "hyderabad": (25.3960, 68.3578),
    }

    c1 = city1.lower().strip()
    c2 = city2.lower().strip()

    if c1 not in cities:
        return json.dumps({"error": f"City '{city1}' not found. Available: {list(cities.keys())}"})
    if c2 not in cities:
        return json.dumps({"error": f"City '{city2}' not found. Available: {list(cities.keys())}"})

    lat1, lon1 = cities[c1]
    lat2, lon2 = cities[c2]

    # Haversine formula
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c

    # Estimate travel time (average speed 80 km/h by road)
    travel_hours = distance / 80
    hours = int(travel_hours)
    minutes = int((travel_hours - hours) * 60)

    return json.dumps({
        "city1": city1.title(),
        "city2": city2.title(),
        "distance_km": round(distance, 1),
        "estimated_travel_time": f"{hours}h {minutes}m",
        "method": "Haversine formula (straight-line distance)",
    }, indent=2)


# ─── Run Server ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting MCP Server: WeatherCurrencyMCPServer")
    print("Tools exposed:")
    print("  1. get_weather_forecast(city, days)")
    print("  2. convert_currency(amount, from_currency, to_currency)")
    print("  3. calculate_distance(city1, city2)")
    print("\nServer running on stdio transport...")
    mcp.run(transport="stdio")
