"""
RentSpider API MCP Server
-------------------------
MCP server that provides real estate property search via RentSpider API
with interactive elicitation for refined search parameters.
"""

import json
import os
import aiohttp
from typing import Optional, Dict, Any
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.elicitation import (
    AcceptedElicitation,
    DeclinedElicitation,
    CancelledElicitation,
)
from pydantic import BaseModel, Field

# Initialize the MCP server
mcp = FastMCP("RentSpider API")

# RentSpider API Configuration
RENTSPIDER_API_KEY = os.getenv("RENTSPIDER_API_KEY")
RENTSPIDER_BASE_URL = "https://api.rentspider.com/v1"


# Elicitation schemas for user preferences
class PropertySearchPreferences(BaseModel):
    min_price: int = Field(default=0, description="Minimum price in USD")
    max_price: int = Field(default=2000000, description="Maximum price in USD")
    min_bedrooms: int = Field(default=1, description="Minimum number of bedrooms")
    max_bedrooms: int = Field(default=10, description="Maximum number of bedrooms")
    property_types: str = Field(
        default="all",
        description="Property types: all, house, condo, townhouse, apartment",
    )
    max_days_on_market: int = Field(
        default=365, description="Maximum days property has been on market"
    )
    sort_by: str = Field(
        default="price_low",
        description="Sort by: price_low, price_high, newest, days_on_market",
    )
    include_rentals: bool = Field(
        default=True, description="Include rental properties in search?"
    )


class MarketAnalysisPreferences(BaseModel):
    analysis_period: str = Field(
        default="12months",
        description="Analysis period: 3months, 6months, 12months, 24months",
    )
    include_forecasts: bool = Field(
        default=True, description="Include market forecasts?"
    )
    compare_neighborhoods: bool = Field(
        default=False, description="Compare different neighborhoods?"
    )
    focus_investment: bool = Field(
        default=False, description="Focus on investment metrics?"
    )


class RentalTrendsPreferences(BaseModel):
    property_size: str = Field(
        default="all",
        description="Property size focus: all, studio, 1br, 2br, 3br, 4br+",
    )
    trend_period: str = Field(
        default="12months",
        description="Trend analysis period: 6months, 12months, 24months",
    )
    include_vacancy_data: bool = Field(
        default=True, description="Include vacancy rate data?"
    )
    seasonal_analysis: bool = Field(
        default=False, description="Include seasonal trend analysis?"
    )


async def make_api_request(
    endpoint: str, params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Make a request to the RentSpider API"""
    if not RENTSPIDER_API_KEY:
        raise ValueError("RENTSPIDER_API_KEY environment variable not set")

    headers = {
        "Authorization": f"Bearer {RENTSPIDER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RENTSPIDER_BASE_URL}/{endpoint}",
                headers=headers,
                params=params,
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"RentSpider API error {response.status}: {error_text}"
                    )
    except Exception as e:
        raise Exception(f"Error calling RentSpider API: {str(e)}")


@mcp.tool()
async def search_properties(location: str, ctx: Context) -> str:
    """
    Search for properties in a specific location using RentSpider API.
    Interactive elicitation will refine search parameters based on user preferences.

    Args:
        location: The city and state (e.g., "Austin, TX")
    """

    if not RENTSPIDER_API_KEY:
        return "Error: RENTSPIDER_API_KEY environment variable not set. Please configure your API key."

    # Elicit search preferences from user
    result = await ctx.elicit(
        message=f"Let's customize your property search for {location}. Please specify your preferences:",
        schema=PropertySearchPreferences,
    )

    match result:
        case AcceptedElicitation(data=prefs):
            # Build API parameters based on user preferences
            api_params = {
                "location": location,
                "min_price": prefs.min_price,
                "max_price": prefs.max_price,
                "min_bedrooms": prefs.min_bedrooms,
                "max_bedrooms": prefs.max_bedrooms,
                "max_days_on_market": prefs.max_days_on_market,
                "sort": prefs.sort_by,
                "limit": 25,  # Reasonable limit for results
            }

            # Add property type filter if not "all"
            if prefs.property_types != "all":
                api_params["property_type"] = prefs.property_types

            # Add rental filter
            if prefs.include_rentals:
                api_params["include_rentals"] = "true"

            try:
                # Make API call to RentSpider
                data = await make_api_request("properties/search", api_params)

                # Format and return results
                response = {
                    "search_criteria": {
                        "location": location,
                        "price_range": f"${prefs.min_price:,} - ${prefs.max_price:,}",
                        "bedrooms": f"{prefs.min_bedrooms} - {prefs.max_bedrooms}",
                        "property_types": prefs.property_types,
                        "max_days_on_market": prefs.max_days_on_market,
                        "sort_by": prefs.sort_by,
                        "include_rentals": prefs.include_rentals,
                    },
                    "api_response": data,
                    "data_source": "RentSpider API",
                }

                return json.dumps(response, indent=2)

            except Exception as e:
                # Fallback response when API fails
                fallback_response = {
                    "search_criteria": {
                        "location": location,
                        "price_range": f"${prefs.min_price:,} - ${prefs.max_price:,}",
                        "bedrooms": f"{prefs.min_bedrooms} - {prefs.max_bedrooms}",
                        "property_types": prefs.property_types,
                        "max_days_on_market": prefs.max_days_on_market,
                        "sort_by": prefs.sort_by,
                        "include_rentals": prefs.include_rentals,
                    },
                    "error": f"RentSpider API unavailable: {str(e)}",
                    "fallback_message": "Use web search for property data instead",
                    "data_source": "API_FAILED",
                }

                return json.dumps(fallback_response, indent=2)

        case DeclinedElicitation():
            return "Property search declined by user."

        case CancelledElicitation():
            return "Property search was cancelled."


@mcp.tool()
async def get_market_statistics(location: str, ctx: Context) -> str:
    """
    Get market statistics for a location using RentSpider API.
    Interactive elicitation customizes the analysis scope and detail level.

    Args:
        location: The city and state (e.g., "Austin, TX")
    """

    if not RENTSPIDER_API_KEY:
        return "Error: RENTSPIDER_API_KEY environment variable not set. Please configure your API key."

    # Elicit analysis preferences
    result = await ctx.elicit(
        message=f"Configure your market analysis for {location}:",
        schema=MarketAnalysisPreferences,
    )

    match result:
        case AcceptedElicitation(data=prefs):
            # Build API parameters
            api_params = {
                "location": location,
                "period": prefs.analysis_period,
                "include_forecasts": str(prefs.include_forecasts).lower(),
                "include_neighborhoods": str(prefs.compare_neighborhoods).lower(),
                "investment_focus": str(prefs.focus_investment).lower(),
            }

            try:
                # Make API call to RentSpider
                data = await make_api_request("market/statistics", api_params)

                # Format and return results
                response = {
                    "search_criteria": {
                        "location": location,
                        "analysis_period": prefs.analysis_period,
                        "include_forecasts": prefs.include_forecasts,
                        "compare_neighborhoods": prefs.compare_neighborhoods,
                        "investment_focus": prefs.focus_investment,
                    },
                    "api_response": data,
                    "data_source": "RentSpider API",
                }

                return json.dumps(response, indent=2)

            except Exception as e:
                # Fallback response when API fails
                fallback_response = {
                    "search_criteria": {
                        "location": location,
                        "analysis_period": prefs.analysis_period,
                        "include_forecasts": prefs.include_forecasts,
                        "compare_neighborhoods": prefs.compare_neighborhoods,
                        "investment_focus": prefs.focus_investment,
                    },
                    "error": f"RentSpider API unavailable: {str(e)}",
                    "fallback_message": "Use web search for market data instead",
                    "data_source": "API_FAILED",
                }

                return json.dumps(fallback_response, indent=2)

        case DeclinedElicitation():
            return "Market analysis declined by user."

        case CancelledElicitation():
            return "Market analysis was cancelled."


@mcp.tool()
async def get_rental_trends(location: str, ctx: Context) -> str:
    """
    Get rental market trends for a location using RentSpider API.
    Interactive elicitation allows customization of trend analysis parameters.

    Args:
        location: The city and state (e.g., "Austin, TX")
    """

    if not RENTSPIDER_API_KEY:
        return "Error: RENTSPIDER_API_KEY environment variable not set. Please configure your API key."

    # Elicit rental analysis preferences
    result = await ctx.elicit(
        message=f"Customize your rental market analysis for {location}:",
        schema=RentalTrendsPreferences,
    )

    match result:
        case AcceptedElicitation(data=prefs):
            # Build API parameters
            api_params = {
                "location": location,
                "period": prefs.trend_period,
                "include_vacancy": str(prefs.include_vacancy_data).lower(),
                "seasonal_analysis": str(prefs.seasonal_analysis).lower(),
            }

            # Add property size filter if not "all"
            if prefs.property_size != "all":
                api_params["property_size"] = prefs.property_size

            try:
                # Make API call to RentSpider
                data = await make_api_request("market/trends", api_params)

                # Format response
                response = {
                    "analysis_config": {
                        "location": location,
                        "property_size_focus": prefs.property_size,
                        "trend_period": prefs.trend_period,
                        "include_vacancy_data": prefs.include_vacancy_data,
                        "seasonal_analysis": prefs.seasonal_analysis,
                    },
                    "rental_trends": data,
                    "data_source": "RentSpider API",
                }

                return json.dumps(response, indent=2)

            except Exception as e:
                # Fallback response when API fails
                fallback_response = {
                    "analysis_config": {
                        "location": location,
                        "property_size_focus": prefs.property_size,
                        "trend_period": prefs.trend_period,
                        "include_vacancy_data": prefs.include_vacancy_data,
                        "seasonal_analysis": prefs.seasonal_analysis,
                    },
                    "error": f"RentSpider API unavailable: {str(e)}",
                    "fallback_message": "Use web search for rental trends data instead",
                    "data_source": "API_FAILED",
                }

                return json.dumps(fallback_response, indent=2)

        case DeclinedElicitation():
            return "Rental trends analysis declined by user."

        case CancelledElicitation():
            return "Rental trends analysis was cancelled."


@mcp.tool()
async def get_property_details(property_id: str) -> str:
    """
    Get detailed information about a specific property using RentSpider API.

    Args:
        property_id: The unique identifier for the property
    """

    if not RENTSPIDER_API_KEY:
        return "Error: RENTSPIDER_API_KEY environment variable not set. Please configure your API key."

    try:
        # Make API call to get property details
        data = await make_api_request(f"properties/{property_id}", {})

        return json.dumps(data, indent=2)

    except Exception as e:
        return f"Error getting property details: {str(e)}"


@mcp.tool()
async def get_comparable_properties(property_id: str, ctx: Context) -> str:
    """
    Get comparable properties (comps) for a specific property using RentSpider API.

    Args:
        property_id: The unique identifier for the property to find comps for
    """

    if not RENTSPIDER_API_KEY:
        return "Error: RENTSPIDER_API_KEY environment variable not set. Please configure your API key."

    # Simple confirmation elicitation
    class CompAnalysisPrefs(BaseModel):
        radius_miles: float = Field(
            default=1.0, description="Search radius in miles for comparable properties"
        )
        max_comps: int = Field(
            default=10, description="Maximum number of comparable properties to return"
        )
        include_pending: bool = Field(
            default=False, description="Include pending sales in comparison?"
        )

    result = await ctx.elicit(
        message=f"Configure comparable property analysis for property {property_id}:",
        schema=CompAnalysisPrefs,
    )

    match result:
        case AcceptedElicitation(data=prefs):
            api_params = {
                "radius": prefs.radius_miles,
                "limit": prefs.max_comps,
                "include_pending": str(prefs.include_pending).lower(),
            }

            try:
                # Make API call to get comparable properties
                data = await make_api_request(
                    f"properties/{property_id}/comparables", api_params
                )

                response = {
                    "property_id": property_id,
                    "comp_analysis_config": {
                        "search_radius_miles": prefs.radius_miles,
                        "max_comparables": prefs.max_comps,
                        "include_pending_sales": prefs.include_pending,
                    },
                    "comparable_properties": data,
                }

                return json.dumps(response, indent=2)

            except Exception as e:
                return f"Error getting comparable properties: {str(e)}"

        case DeclinedElicitation():
            return "Comparable property analysis declined by user."

        case CancelledElicitation():
            return "Comparable property analysis was cancelled."


def main():
    """Main entry point for the RentSpider MCP server."""
    if not RENTSPIDER_API_KEY:
        print("Warning: RENTSPIDER_API_KEY environment variable not set!")
        print("Set it with: export RENTSPIDER_API_KEY='your-api-key'")
        print(
            "The server will start but API calls will fail until the key is configured."
        )

    mcp.run()


if __name__ == "__main__":
    main()
