# orchestrator.py
import streamlit as st
import requests
import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv('.env.boutique')
load_dotenv()  # Load GOOGLE_API_KEY

# Configure Gemini
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    st.error("GOOGLE_API_KEY not found in .env")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)

# Get available models and select the best one
available_models = [model.name for model in genai.list_models()]

# Try different model names in order of preference
model_names = [
    'gemini-pro',
    'gemini-1.0-pro',
    'gemini-1.5-pro',
    'gemini-2.0-pro',
    'gemini-2.5-pro'
]

selected_model = None
for name in model_names:
    if name in available_models:
        selected_model = name
        break
    # Try with models/ prefix
    full_name = f"models/{name}"
    if full_name in available_models:
        selected_model = full_name
        break

if not selected_model:
    st.error("No suitable Gemini model found. Available models: " + ", ".join(available_models))
    st.stop()

# Initialize Gemini model
model = genai.GenerativeModel(selected_model)

# Set up API endpoints
ORDER_AGENT_URL = "http://localhost:8001"
BOUTIQUE_API_URL = os.getenv('BOUTIQUE_API_URL')

if not BOUTIQUE_API_URL:
    st.error("BOUTIQUE_API_URL not found in .env.boutique")
    st.stop()

st.title("🧩 Orchestrator AI Agent (MCP + Gemini)")

# Step 1: Discover available agents and their capabilities
@st.cache_resource
def discover_agent_capabilities():
    capabilities = {
        "order_agent": [],
        "payment_agent": []
    }
    
    # Discover MCP tools from Order Agent
    try:
        response = requests.get(f"{ORDER_AGENT_URL}/.well-known/mcp")
        if response.status_code == 200:
            capabilities["order_agent"] = response.json()["tools"]
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to Order Agent")
    except Exception as e:
        st.error(f"Error discovering Order Agent capabilities: {str(e)}")
    
    # Discover A2A capabilities from Payment Agent
    try:
        response = requests.get("http://localhost:8003/.well-known/agent-capabilities")
        if response.status_code == 200:
            agent_info = response.json()
            capabilities["payment_agent"] = agent_info["capabilities"]
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to Payment Agent")
    except Exception as e:
        st.error(f"Error discovering Payment Agent capabilities: {str(e)}")
    
    return capabilities

# Discover agent capabilities (without displaying)
agent_capabilities = discover_agent_capabilities()


# Step 2: User input
user_input = st.text_input("Ask me something (e.g., 'show products', 'order 2 laptops')")


async def ask_gemini(prompt: str) -> str:
    """Call Gemini model and return output."""
    try:
        # Configure generation settings
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,  # Lower temperature for more consistent JSON
            candidate_count=1,
            stop_sequences=["}"],  # Stop after JSON object
            max_output_tokens=1000,
            top_p=0.8,
            top_k=40
        )
        
        # Configure safety settings
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE",
            },
        ]
        
        # Generate response
        response = await model.generate_content_async(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Extract text from response
        if response.text:
            return response.text.strip()
        
        # Fallback: try to get text from parts
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.text:
                    return part.text.strip()
        
        raise ValueError("No content in Gemini response")
    except Exception as e:
        st.error(f"Gemini API error: {str(e)}")
        return "{}"  # Return empty JSON as fallback


def safe_json_parse(raw_output: str) -> dict:
    """
    Parse AI model output into JSON even if it's slightly malformed.
    """
    raw_output = raw_output.strip()

    # Try direct parse
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        pass

    # Try extracting the largest {...} block
    start = raw_output.find("{")
    end = raw_output.rfind("}")
    if start != -1 and end != -1:
        candidate = raw_output[start:end+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try auto-fix: ensure closing braces match
    open_braces = raw_output.count("{")
    close_braces = raw_output.count("}")
    if open_braces > close_braces:
        fixed = raw_output + "}" * (open_braces - close_braces)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # Last resort: strip everything except valid JSON chars
    candidate = re.findall(r"\{.*\}", raw_output, re.DOTALL)
    if candidate:
        try:
            return json.loads(candidate[0])
        except:
            pass

    raise ValueError(f"Failed to parse AI output after repairs: {raw_output}")


# Step 3: Map natural language to tool using Gemini
if st.button("Run"):
    st.info("🤔 Analyzing your request...")

    # First get product list to include in prompt
    try:
        st.info("🔄 Executing listProducts...")
        products_response = requests.post(f"{ORDER_AGENT_URL}/invoke/listProducts")
        if products_response.status_code != 200:
            st.error(f"❌ Failed to execute listProducts: {products_response.text}")
            st.stop()
            
        result = products_response.json()
        if not result.get("products"):
            st.warning("⚠️ No products available")
            st.stop()
            
        available_products = result["products"]
        st.success(f"📦 Found {len(available_products)} products")
        
        # Create detailed product list with prices and descriptions
        product_details = []
        for p in available_products:
            price = float(p.get('priceUsd', 0))
            desc = p.get('description', '').split('.')[0]  # Get first sentence of description
            product_details.append(f"- {p['name']}: ${price:.2f}")
            product_details.append(f"  ID: {p['id']}")
            product_details.append(f"  Description: {desc}")
            product_details.append("")  # Add blank line
        products_text = "\n".join(product_details)
        
        # Create product ID reference
        id_list = []
        for p in available_products:
            id_list.append(f"- {p['id']} ({p['name']})")
        valid_ids = "\n".join(id_list)
            
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to Order Agent: {str(e)}")
        st.stop()

    # Extract valid product IDs for validation
    valid_product_ids = [p['id'] for p in available_products]
    
    # Get tools from agent capabilities
    order_tools = agent_capabilities.get("order_agent", [])
    if not order_tools:
        st.error("❌ No Order Agent tools discovered. Is the Order Agent running?")
        st.stop()

    # Create tool documentation
    tool_docs = []
    for tool in order_tools:
        name = tool.get("name", "")
        description = tool.get("description", "No description available")
        input_schema = tool.get("input_schema", {})
        output_schema = tool.get("output_schema", {})
        
        # Create example args based on schema
        example_args = {}
        for param_name, param_type in input_schema.items():
            if param_type == "string" and param_name == "product_id":
                example_args[param_name] = valid_product_ids[0] if valid_product_ids else "EXAMPLE_ID"
            elif param_type == "string":
                example_args[param_name] = f"example_{param_name}"
            elif param_type == "integer":
                example_args[param_name] = 1
            elif param_type == "number":
                example_args[param_name] = 1.0
            else:
                example_args[param_name] = f"<{param_type}>"
        
        tool_docs.append(f"""
        Tool: {name}
        Description: {description}
        Input Schema: {json.dumps(input_schema, indent=2)}
        Output Schema: {json.dumps(output_schema, indent=2)}
        Example: {{"tool": "{name}", "args": {json.dumps(example_args, indent=2)}}}
        """)

    # Extract available tool names
    available_tool_names = [t.get("name") for t in order_tools if t.get("name")]  # Get non-empty tool names
    
    # Find list and order tools
    list_tool = next((t for t in order_tools if any(word in t.get("name", "").lower() or word in t.get("description", "").lower() for word in ["list", "show", "display", "get"])), None)
    order_tool = next((t for t in order_tools if any(word in t.get("name", "").lower() or word in t.get("description", "").lower() for word in ["order", "buy", "purchase", "place"])), None)

    # Create the prompt
    prompt = (
        f"You are a JSON-focused API orchestrator for an online boutique. Your responses must be PURE JSON - no markdown, no explanations, no extra text.\n\n"
        f"AVAILABLE TOOLS:\n"
        f"{chr(10).join(tool_docs)}\n\n"
        f"STRICT RESPONSE FORMAT:\n"
        f'{{"tool": "<TOOL_NAME>", "args": <TOOL_PARAMETERS>}}\n'
        f"Where TOOL_NAME must be one of: {available_tool_names}\n\n"
        f"RULES:\n"
        f"1. Response MUST be a single JSON object\n"
        f"2. No text before or after the JSON\n"
        f"3. No comments or explanations\n"
        f"4. No markdown formatting\n"
        f"5. Valid product IDs: {valid_product_ids}\n"
        f"6. For order operations: quantity must be > 0\n"
        f"7. IMPORTANT: If user asks for a product that does not exist:\n"
        f"   - ALWAYS use the list/display tool\n"
        f"   - Do not try to guess or substitute products\n"
        f'   - Example: "order cooker" -> use list tool because cooker is not in catalog\n'
        f"8. Default to list/display tool if:\n"
        f"   - User asks to see products\n"
        f"   - Product does not exist or is not found\n"
        f"   - Intent is unclear\n"
        f"   - You are not 100% sure about the product\n\n"
        f"AVAILABLE PRODUCTS:\n"
        f"{products_text}\n\n"
        f"EXAMPLE INPUTS AND OUTPUTS:\n"
        f'Input: "show me what you have"\n'
        f'Output: {{"tool": "{list_tool["name"] if list_tool else "listProducts"}", "args": {{}}}}\n\n'
        f'Input: "display available products"\n'
        f'Output: {{"tool": "{list_tool["name"] if list_tool else "listProducts"}", "args": {{}}}}\n\n'
        f'Input: "I want to buy 2 sunglasses"\n'
        f'Output: {{"tool": "{order_tool["name"] if order_tool else "placeOrder"}", "args": {{"product_id": "{valid_product_ids[0]}", "quantity": 2}}}}\n\n'
        f'Input: "order a {available_products[0]["name"] if available_products else "product"}"\n'
        f'Output: {{"tool": "{order_tool["name"] if order_tool else "placeOrder"}", "args": {{"product_id": "{valid_product_ids[0]}", "quantity": 1}}}}\n\n'
        f'USER INPUT: "{user_input}"\n\n'
        f"RESPOND WITH JSON ONLY:"
    )
    ai_response = asyncio.run(ask_gemini(prompt))
    try:
        decision = safe_json_parse(ai_response)
        tool_name = decision["tool"]
        args = decision["args"]
        
        # Extract product name from user input
        def extract_product_name(input_text):
            # Common words to ignore
            ignore_words = {
                'show', 'me', 'get', 'list', 'display', 'what', 'do', 'you', 'have',
                'order', 'buy', 'purchase', 'want', 'need', 'looking', 'for', 'a', 'an', 'the',
                'some', 'few', 'many', 'please', 'can', 'could', 'would', 'like', 'to'
            }
            
            # Split and clean input
            words = input_text.lower().split()
            
            # If it's just "show products" or similar, don't extract product
            if set(words).issubset({'show', 'products', 'list', 'all', 'available'}):
                return None
                
            # Remove ignored words
            product_terms = [word for word in words if word not in ignore_words]
            
            if product_terms:
                return ' '.join(product_terms)
            return None
        
        product_name = extract_product_name(user_input)
        
        # Get tool specification
        tool_spec = next((t for t in agent_capabilities["order_agent"] if t["name"] == tool_name), None)
        if not tool_spec:
            st.error(f"Tool specification not found for {tool_name}")
            st.stop()
            
        # Check if this is a product listing tool
        if "products" in tool_spec.get("output_schema", {}) and product_name:
            # Check if this was a failed product search
            if any(word in user_input.lower() for word in ['order', 'buy', 'purchase', 'want']):
                st.error(f"❌ Product '{product_name}' is not available in our catalog. Here are our available products:")
            else:
                st.info("📦 Showing all available products:")
        
        # Extra validation for order tools
        if "order" in tool_spec.get("output_schema", {}):
            # Get latest product list for validation
            try:
                # Find the product listing tool
                list_tool = next((t for t in agent_capabilities["order_agent"] if "products" in t.get("output_schema", {})), None)
                if not list_tool:
                    st.error("No product listing tool found")
                    st.stop()
                    
                validate_response = requests.post(f"{ORDER_AGENT_URL}/invoke/{list_tool['name']}")
                if validate_response.status_code == 200:
                    valid_products = validate_response.json().get("products", [])
                    valid_ids = [p["id"] for p in valid_products]
                    
                    if args.get("product_id") not in valid_ids:
                        st.error(f"Invalid product ID: {args.get('product_id')}. Showing available products instead.")
                        # Switch to product listing tool
                        tool_name = list_tool["name"]
                        args = {}
            except Exception as e:
                st.warning(f"Could not validate product ID: {str(e)}. Proceeding with order...")

        # Step 4: Call the appropriate tool
        try:
            # Validate tool exists in capabilities
            available_tools = [tool["name"] for tool in agent_capabilities.get("order_agent", [])]
            if tool_name not in available_tools:
                st.error(f"Unknown tool: {tool_name}. Available tools: {', '.join(available_tools)}")
                st.stop()
                
            # Get tool specification
            tool_spec = next((t for t in agent_capabilities["order_agent"] if t["name"] == tool_name), None)
            if not tool_spec:
                st.error(f"Tool specification not found for {tool_name}")
                st.stop()
                
            # Validate required parameters
            required_params = tool_spec.get("input_schema", {})
            missing_params = [param for param in required_params if param not in args]
            if missing_params:
                st.error(f"Missing required parameters: {', '.join(missing_params)}")
                st.write("Tool specification:", tool_spec)
                st.stop()
            
            # Make the API call to Order Agent
            try:
                response = requests.post(f"{ORDER_AGENT_URL}/invoke/{tool_name}", json=args)
                if response.status_code != 200:
                    error_msg = response.text
                    try:
                        error_details = response.json()
                        if 'detail' in error_details:
                            error_msg = error_details['detail']
                    except:
                        pass
                    st.error(f"Order operation failed: {error_msg}")
                    st.write("Debug Information:")
                    st.write(f"- Order Agent URL: {ORDER_AGENT_URL}")
                    st.write(f"- Tool: {tool_name}")
                    st.write(f"- Args: {args}")
                    st.write(f"- Response: {response.text}")
                    st.stop()
                    
                result = response.json()
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to Order Agent: {str(e)}")
                st.stop()
            except Exception as e:
                st.error(f"Unexpected error calling Order Agent: {str(e)}")
                st.stop()
            
            # Get tool specification
            tool_spec = next((t for t in agent_capabilities["order_agent"] if t["name"] == tool_name), None)
            if not tool_spec:
                st.error(f"Tool specification not found for {tool_name}")
                st.stop()

            # Handle response based on tool's output schema
            output_schema = tool_spec.get("output_schema", {})
            
            # Handle product listing tools (tools that return a list of products)
            if "products" in output_schema:
                if not result.get('products'):
                    st.warning("No products available")
                    st.stop()
                if not product_name:
                    st.write("📦 Available Products:")
                st.markdown("---")  # Add separator
                for product in result["products"]:
                    price_usd = float(product.get('priceUsd', 0))
                    name = product['name']
                    product_id = product['id']
                    desc = product.get('description', 'No description available')
                    
                    # Create a clean, compact display
                    st.markdown(f"""
                    ### {name}
                    **${price_usd:.2f}** | ID: `{product_id}`
                    
                    {desc}
                    
                    ---
                    """)
                    
            # Handle order creation tools (tools that return an order object)
            elif "order" in output_schema:
                # Get latest products from Online Boutique
                try:
                    # Get product details from Order Agent since it already has the parsed data
                    list_tool = next((t for t in agent_capabilities["order_agent"] if "products" in t.get("output_schema", {})), None)
                    if not list_tool:
                        st.error("No product listing tool found")
                        st.stop()
                        
                    product_response = requests.post(f"{ORDER_AGENT_URL}/invoke/{list_tool['name']}")
                    if product_response.status_code != 200:
                        st.error(f"Failed to fetch product details: {product_response.text}")
                        st.stop()
                    
                    products = product_response.json().get("products", [])
                    valid_product = next((p for p in products if p["id"] == args["product_id"]), None)
                    
                    if not valid_product:
                        st.error(f"Invalid product ID: {args['product_id']}. Please choose from available products.")
                        st.stop()
                        
                except requests.exceptions.RequestException as e:
                    st.error(f"Error connecting to Order Agent: {e}")
                    st.stop()
                
                if args["quantity"] <= 0:
                    st.error("Quantity must be positive")
                    st.stop()
                    
                # Process the order
                order = result["order"]
                st.success("Order placed successfully!")
                st.markdown(f"""
                #### Order Details:
                - **Order ID:** `{order['order_id']}`
                - **Tracking ID:** `{order.get('tracking_id', 'Unknown')}`
                - **Product ID:** `{order['product_id']}`
                - **Quantity:** {order['quantity']}
                - **Total Paid:** ${order.get('total_paid', 0.0):.2f}
                - **Status:** {order['status']}
                """)
                
                # Calculate total amount using price from Online Boutique
                total_amount = float(valid_product.get("priceUsd", 0)) * args["quantity"]
                
                # Automatically handle payment after successful order
                try:
                    st.info("Processing payment...")
                    payment_resp = requests.post(
                        "http://localhost:8003/a2a/processPayment",
                        json={
                            "message_type": "request",
                            "sender": "orchestrator_agent",
                            "intent": "process_payment",
                            "conversation_id": f"order_{order['order_id']}",
                            "payload": {
                                "message": f"Process payment of ${total_amount} for order {order['order_id']}",
                                "context": {
                                    "order_id": order['order_id'],
                                    "product": valid_product,
                                    "quantity": args["quantity"],
                                    "total_amount": total_amount
                                }
                            }
                        }
                    )
                    
                    if payment_resp.status_code == 200:
                        payment_result = payment_resp.json()
                        if payment_result.get('message_type') == 'error':
                            st.error(f"❌ Payment failed: {payment_result.get('payload', {}).get('error', 'Unknown error')}")
                        else:
                            # Extract transaction ID from the A2A response payload
                            transaction_id = payment_result.get('payload', {}).get('transaction_id', 'Unknown')
                            st.success(f"💳 Payment processed successfully! Transaction ID: {transaction_id}")
                            
                            # Display payment details in a clean format
                            payment_details = payment_result.get('payload', {})
                            st.markdown("""
                            #### Payment Details:
                            """)
                            for key, value in payment_details.items():
                                if key != 'transaction_id':  # Already shown above
                                    st.markdown(f"- **{key.replace('_', ' ').title()}:** {value}")
                    else:
                        st.error(f"❌ Payment failed: {payment_resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error("Could not connect to Payment AI Agent. Is it running?")
                except Exception as e:
                    st.error(f"Unexpected error processing payment: {str(e)}")
                    
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to Order Agent. Is it running?")
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")

    except Exception as e:
        st.error(f"Failed to parse AI output: {e}")