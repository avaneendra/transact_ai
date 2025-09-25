# order_agent_mcp.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import os
import aiohttp
import asyncio
from bs4.element import Tag
from dotenv import load_dotenv
import re
from bs4 import BeautifulSoup
import traceback
import time
from datetime import datetime, timedelta

app = FastAPI(title="Order Agent (MCP Server)")

# Load environment variables
load_dotenv('.env.boutique')
BOUTIQUE_API_URL = os.getenv('BOUTIQUE_API_URL')

if not BOUTIQUE_API_URL:
    raise ValueError("BOUTIQUE_API_URL not found in .env.boutique")

# Create aiohttp session for async requests
async def get_session():
    return aiohttp.ClientSession()

# Cache for products with timeout
_products_cache = None
_cache_timestamp = None
CACHE_TIMEOUT = timedelta(minutes=5)  # Refresh cache every 5 minutes

async def get_products():
    """Get products from Online Boutique with caching and auto-refresh"""
    global _products_cache, _cache_timestamp
    
    # Check if cache is valid
    if _products_cache is not None and _cache_timestamp is not None:
        if datetime.now() - _cache_timestamp < CACHE_TIMEOUT:
            return _products_cache
    
    products = []
    print(f"Fetching products from {BOUTIQUE_API_URL}")
    
    try:
        # Get the homepage to discover products
        endpoints = ['/']  # Only need homepage to get product IDs
        
        products_found = False
        product_ids = []  # Initialize product_ids here
        
        for endpoint in endpoints:
            try:
                url = f"{BOUTIQUE_API_URL.rstrip('/')}{endpoint}"
                print(f"Trying endpoint: {url}")
                async with await get_session() as session:
                    async with session.get(url) as response:
                        print(f"Response status: {response.status}")
                        print(f"Response headers: {response.headers.get('content-type', 'unknown')}")
                        text = await response.text()
                        print(f"Response body: {text[:200]}...")  # Print first 200 chars
                
                if response.status == 200:
                    # Try parsing as JSON first
                    try:
                        data = await response.json()
                        if isinstance(data, list):
                            print("Found product list in JSON response")
                            products = data
                            products_found = True
                            break
                        elif isinstance(data, dict) and 'products' in data:
                            print("Found products in JSON response")
                            products = data['products']
                            products_found = True
                            break
                    except:
                        # If not JSON, try HTML parsing
                        if 'text/html' in response.headers.get('content-type', ''):
                            print("Parsing HTML for product links")
                            # Look for product links or data
                            soup = BeautifulSoup(text, 'html.parser')
                            product_links = soup.find_all('a', href=re.compile(r'/product/[A-Z0-9]+'))
                            
                            for link in product_links:
                                # Extract product ID from href
                                match = re.search(r'/product/([A-Z0-9]+)', link['href'])
                                if match:
                                    product_id = match.group(1)
                                    # Skip if in "You May Also Like" section
                                    if not link.find_parent(class_='recommendations'):
                                        product_ids.append(product_id)
                            
                            if product_ids:
                                print(f"Found product IDs in HTML: {product_ids}")
                                break
            except Exception as e:
                print(f"Error trying endpoint {endpoint}: {e}")
                continue
        
        if not products_found and not product_ids:
            print("No products found through any endpoint")
            return _products_cache if _products_cache else []
            
        # If we found product IDs in HTML, fetch details for each
        if not products_found and product_ids:
            for product_id in set(product_ids):  # Use set to remove duplicates
                try:
                    # Use the correct product endpoint
                    detail_endpoints = [f"/product/{product_id}"]
                    
                    for endpoint in detail_endpoints:
                        try:
                            url = f"{BOUTIQUE_API_URL.rstrip('/')}{endpoint}"
                            print(f"Trying product endpoint: {url}")
                            async with await get_session() as session:
                                async with session.get(url) as response:
                                    print(f"Response status: {response.status}")
                                    content_type = response.headers.get('content-type', '').lower()
                                    text = await response.text()
                                    
                                    if response.status == 200:
                                        if 'application/json' in content_type:
                                            try:
                                                product = await response.json()
                                                if isinstance(product, dict) and ('id' in product or 'name' in product):
                                                    products.append(product)
                                                    print(f"Successfully fetched product {product_id} from JSON")
                                                    break
                                            except:
                                                print(f"Invalid JSON for product {product_id}")
                                                continue
                                        elif 'text/html' in content_type:
                                            try:
                                                print(f"Parsing HTML for product {product_id}")
                                                print(f"HTML content: {text[:500]}...")  # Print first 500 chars
                                                
                                                soup = BeautifulSoup(text, 'html.parser')
                                                
                                                # Find all h2 tags and their prices
                                                h2_tags = soup.find_all('h2')
                                                print(f"Found {len(h2_tags)} h2 tags")
                                                
                                                for h2 in h2_tags:
                                                    print(f"Processing h2: {h2.text.strip()}")
                                                    
                                                    # Get all text after this h2 until the next h2 or end
                                                    price_text = None
                                                    desc_text = None
                                                    
                                                    # Skip "You May Also Like" section
                                                    if h2.text.strip() == 'You May Also Like':
                                                        print("Skipping 'You May Also Like' section")
                                                        continue

                                                    # Extract product details from HTML based on actual structure
                                                    # Product name is in h2 tag
                                                    name = h2
                                                    
                                                    # Find price and description
                                                    price_text = None
                                                    desc_text = None
                                                    
                                                    # First find the price in the text node that contains $
                                                    current = name
                                                    while current and not price_text:
                                                        if isinstance(current, str) and '$' in current:
                                                            price_match = re.search(r'\$(\d+\.?\d*)', current)
                                                            if price_match:
                                                                price_text = price_match.group(1)
                                                                print(f"Found price: ${price_text}")
                                                        current = current.next_sibling
                                                    
                                                    # If we didn't find price yet, look in the next few nodes
                                                    if not price_text:
                                                        for sibling in name.find_next_siblings():
                                                            if isinstance(sibling, Tag) and sibling.name == 'h2':
                                                                break
                                                            if isinstance(sibling, str) and '$' in sibling:
                                                                price_match = re.search(r'\$(\d+\.?\d*)', sibling)
                                                                if price_match:
                                                                    price_text = price_match.group(1)
                                                                    print(f"Found price: ${price_text}")
                                                                    break
                                                            elif isinstance(sibling, Tag) and sibling.name == 'p':
                                                                if '$' in sibling.text:
                                                                    price_match = re.search(r'\$(\d+\.?\d*)', sibling.text)
                                                                    if price_match:
                                                                        price_text = price_match.group(1)
                                                                        print(f"Found price: ${price_text}")
                                                                        break
                                                                else:
                                                                    desc_text = sibling.text.strip()
                                                                    print(f"Found description: {desc_text}")
                                                                    
                                                    # If still no description, look for it
                                                    if not desc_text:
                                                        desc = name.find_next('p')
                                                        if desc and not desc.find_previous('h2', text='You May Also Like'):
                                                            desc_text = desc.text.strip()
                                                            if not '$' in desc_text:
                                                                print(f"Found description: {desc_text}")
                                                    
                                                    print(f"Found in HTML - Name: {name.text.strip() if name else 'None'}")
                                                    print(f"Found in HTML - Price: {price_text if price_text else 'None'}")
                                                    print(f"Found in HTML - Desc: {desc_text if desc_text else 'None'}")
                                                    
                                                    # Create product if we have at least name and either price or description with price
                                                    if name:
                                                        # If we don't have price yet, check description
                                                        if not price_text and desc_text and '$' in desc_text:
                                                            price_match = re.search(r'\$(\d+\.?\d*)', desc_text)
                                                            if price_match:
                                                                price_text = price_match.group(1)
                                                                # Remove price from description
                                                                desc_text = re.sub(r'\$\d+\.?\d*', '', desc_text).strip()
                                                        
                                                        if price_text:  # Now we should have the price
                                                            product = {
                                                                'id': product_id,
                                                                'name': name.text.strip(),
                                                                'priceUsd': float(price_text),
                                                                'description': desc_text if desc_text else 'No description available'
                                                            }
                                                            # Only add if not already in products
                                                            if not any(p.get('id') == product_id for p in products):
                                                                products.append(product)
                                                                print(f"Successfully extracted product {product_id} from HTML")
                                                                print(f"Product details: {product}")
                                                            break
                                                        else:
                                                            print(f"Could not find price for product {product_id}")
                                                    
                                                if not products:
                                                    print("No valid products found in HTML")
                                                    
                                            except Exception as e:
                                                print(f"Error parsing HTML for product {product_id}: {e}")
                                                print(f"Traceback: {traceback.format_exc()}")
                                                continue
                        except Exception as e:
                            print(f"Error with endpoint {endpoint}: {e}")
                            continue
                            
                except Exception as e:
                    print(f"Error fetching product {product_id}: {e}")
                    continue
                
        if products:
            _products_cache = products
            _cache_timestamp = datetime.now()
            print(f"Cached {len(products)} products at {_cache_timestamp}")
        elif _products_cache:
            print("Failed to fetch new products, using cached data")
        else:
            print("No products available")
            
    except aiohttp.ClientError as e:
        print(f"Failed to connect to Online Boutique: {e}")
        if _products_cache:
            print("Using cached data due to connection error")
        else:
            print("No cached data available")
            
    return _products_cache if _products_cache else []

ORDERS = []


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: Dict
    output_schema: Dict


@app.get("/.well-known/mcp")
def discover_tools():
    """MCP Discovery Endpoint: list available tools"""
    return {
        "tools": [
            ToolSpec(
                name="listProducts",
                description="List all available products",
                input_schema={},
                output_schema={"products": "array of product objects"}
            ).dict(),
            ToolSpec(
                name="placeOrder",
                description="Place a new order by product_id and quantity",
                input_schema={"product_id": "integer", "quantity": "integer"},
                output_schema={"order": "order object"}
            ).dict(),
        ]
    }


@app.post("/invoke/listProducts")
async def list_products():
    """List all products from Online Boutique"""
    print("Fetching products from Online Boutique")
    products = await get_products()
    return {"products": products}


@app.post("/invoke/placeOrder")
async def place_order(order: Dict):
    """Place order with Online Boutique"""
    try:
        # Get product details
        products = await get_products()
        product = next((p for p in products if p["id"] == order["product_id"]), None)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
            
        async with await get_session() as session:
            try:
                # First add to cart
                # The API expects form data with specific field names
                cart_data = {
                    "product_id": str(order["product_id"]),
                    "quantity": str(order["quantity"])
                }
                print(f"Adding to cart: {cart_data}")
                cart_response = await session.post(
                    f"{BOUTIQUE_API_URL}/cart",
                    data=cart_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                cart_text = await cart_response.text()
                print(f"Cart response status: {cart_response.status}")
                print(f"Cart response headers: {dict(cart_response.headers)}")
                print(f"Cart response body: {cart_text}")
                
                if cart_response.status != 200:
                    print(f"Cart error: {cart_response.status}, {cart_text}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to add to cart: {cart_text}"
                    )
                
                # Get the session cookie from the cart response
                session_cookie = None
                set_cookie_header = cart_response.headers.get('Set-Cookie', '')
                if 'shop_session-id=' in set_cookie_header:
                    # Extract session ID from Set-Cookie header
                    # Format: shop_session-id=XXXX; Max-Age=172800
                    cookie_parts = set_cookie_header.split(';')
                    for part in cookie_parts:
                        if 'shop_session-id=' in part:
                            session_cookie = part.split('=')[1].strip()
                            break
                
                print(f"Extracted session cookie: {session_cookie}")
                
                if not session_cookie:
                    raise HTTPException(status_code=500, detail="No session cookie found")

                # Then checkout
                # The API expects snake_case field names
                checkout_data = {
                    "email": "test@example.com",
                    "street_address": "1600 Amphitheatre Parkway",
                    "zip_code": "94043",
                    "city": "Mountain View",
                    "state": "CA",
                    "country": "United States",
                    "credit_card_number": "4432801561520454",
                    "credit_card_expiration_month": "01",
                    "credit_card_expiration_year": "2026",
                    "credit_card_cvv": "123"
                }
                print(f"Checking out: {checkout_data}")
                checkout_response = await session.post(
                    f"{BOUTIQUE_API_URL}/cart/checkout",
                    data=checkout_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Cookie": f"shop_session-id={session_cookie}"
                    }
                )
                checkout_text = await checkout_response.text()
                print(f"Checkout response status: {checkout_response.status}")
                print(f"Checkout response headers: {dict(checkout_response.headers)}")
                print(f"Checkout response body: {checkout_text}")
                
                checkout_response.raise_for_status()
                
                # Extract order ID and tracking ID from HTML response
                order_id_match = re.search(r'Confirmation #\s*</div>\s*<div[^>]*>\s*([a-f0-9-]+)', checkout_text)
                tracking_id_match = re.search(r'Tracking #\s*</div>\s*<div[^>]*>\s*([A-Z0-9-]+)', checkout_text)
                total_match = re.search(r'Total Paid\s*</div>\s*<div[^>]*>\s*\$([0-9.]+)', checkout_text)
                
                order_id = order_id_match.group(1).strip() if order_id_match else "unknown"
                tracking_id = tracking_id_match.group(1).strip() if tracking_id_match else "unknown"
                total_paid = float(total_match.group(1)) if total_match else 0.0
                
                print(f"Extracted order ID: {order_id}")
                print(f"Extracted tracking ID: {tracking_id}")
                print(f"Total paid: ${total_paid:.2f}")
                
                # Create local order entry
                order_entry = {
                    "order_id": order_id,
                    "tracking_id": tracking_id,
                    "product_id": order["product_id"],
                    "quantity": order["quantity"],
                    "total_paid": total_paid,
                    "status": "confirmed"
                }
                ORDERS.append(order_entry)
                
                return {"order": order_entry}
            except aiohttp.ClientError as e:
                raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
            finally:
                await session.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process order: {str(e)}")