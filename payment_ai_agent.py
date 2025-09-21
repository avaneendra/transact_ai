# payment_agent_ai.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json
import google.generativeai as genai
import os
import asyncio
from typing import Dict, List, Optional

app = FastAPI(title="Payment AI Agent")

PAYMENT_SERVER = "http://localhost:8002/createPayment"

class AgentMessage(BaseModel):
    message_type: str  # "request", "response", "error"
    sender: str
    intent: str
    payload: Dict
    conversation_id: Optional[str] = None

class AgentCapability(BaseModel):
    name: str
    description: str
    input_schema: Dict
    output_schema: Dict

# Configure Gemini AI
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

genai.configure(api_key=GOOGLE_API_KEY)

# List available models and find the best one for our use case
available_models = [m.name for m in genai.list_models()]
print("Available Gemini models:", available_models)

# Clean model names (remove 'models/' prefix) and find best match
clean_models = [m.replace('models/', '') for m in available_models]
print("Available clean model names:", clean_models)

# Try to find the best available model
if "gemini-2.5-pro" in clean_models:
    MODEL_NAME = "gemini-2.5-pro"  # Latest stable version
elif "gemini-1.5-pro" in clean_models:
    MODEL_NAME = "gemini-1.5-pro"  # Previous stable version
else:
    # Default to pro model
    MODEL_NAME = "gemini-pro"

print(f"Using Gemini model: {MODEL_NAME}")

# Create the model with default settings
model = genai.GenerativeModel(model_name=MODEL_NAME)

async def gemini_infer(prompt: str, max_retries: int = 3) -> str:
    """Call Gemini AI model and return structured response with retries."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Create a simple, direct prompt
            full_prompt = f"""Return ONLY a JSON object with payment details.
Keys: "order_id" (integer), "amount" (number), "method" (string: "credit_card", "paypal", or "bank_transfer")
Example: {{"order_id": 123, "amount": 99.99, "method": "credit_card"}}

Input: {prompt}"""

            print(f"\nAttempt {attempt + 1}/{max_retries}")
            print("Prompt:", full_prompt)

            # Simple generation with minimal parameters
            response = await model.generate_content_async(
                full_prompt,
                generation_config={"temperature": 0.1}
            )
            
            print("Response object:", response)
            
            if not response:
                raise ValueError("Empty response from Gemini")
                
            # Get response text
            result = response.text
            if not result:
                raise ValueError("Empty text in response")
                
            print("Raw result:", result)
            
            # Basic cleaning
            result = result.strip()
            result = result.replace('```json', '').replace('```', '')
            result = result.strip()
            
            # Validate it's parseable JSON
            try:
                json.loads(result)
                return result
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
                
        except Exception as e:
            last_error = e
            error_msg = f"Attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}"
            print(error_msg)
            
            if attempt < max_retries - 1:
                print(f"Retrying... ({attempt + 2}/{max_retries})")
                await asyncio.sleep(1)  # Wait a bit before retrying
                continue
            
            # If all retries failed, raise the last error
            error_msg = f"All {max_retries} attempts failed. Last error: {type(last_error).__name__}: {str(last_error)}"
            print(error_msg)
            raise ValueError(error_msg)

@app.get("/.well-known/agent-capabilities")
async def get_capabilities():
    """A2A Protocol: Advertise agent capabilities"""
    return {
        "agent_id": "payment_ai_agent",
        "capabilities": [
            AgentCapability(
                name="processPayment",
                description="Process payment for an order using natural language understanding",
                input_schema={
                    "message": "string",  # Natural language payment request
                    "context": "object"   # Optional context about the order
                },
                output_schema={
                    "status": "string",
                    "transaction_id": "string",
                    "details": "object"
                }
            ).model_dump()
        ]
    }

@app.post("/a2a/processPayment")
async def process_payment(message: AgentMessage):
    """A2A Protocol: Handle payment processing request from other agents"""
    try:
        # Get context and message
        context = message.payload.get('context', {})
        input_text = message.payload.get('message', '')
        
        # Extract structured details
        order_id = context.get('order_id')
        amount = context.get('total_amount')
        
        # Create a simple, structured input
        structured_input = f"Order #{order_id} with amount ${amount}. Use credit_card as payment method."
        
        try:
            # Get JSON response from Gemini
            json_response = await gemini_infer(structured_input)
            print("Gemini JSON response:", json_response)
            
            # Process payment
            payment_response = requests.post(PAYMENT_SERVER, json=json.loads(json_response))
            
            if payment_response.status_code != 200:
                raise HTTPException(
                    status_code=payment_response.status_code,
                    detail=f"Payment server error: {payment_response.text}"
                )
            
            # Return A2A protocol response
            return AgentMessage(
                message_type="response",
                sender="payment_ai_agent",
                intent="payment_processed",
                conversation_id=message.conversation_id,
                payload=payment_response.json()
            ).model_dump()
            
        except Exception as e:
            error_msg = f"Payment processing error: {str(e)}"
            print(error_msg)
            return AgentMessage(
                message_type="error",
                sender="payment_ai_agent",
                intent="payment_failed",
                conversation_id=message.conversation_id,
                payload={"error": error_msg}
            ).model_dump()
            
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)
        return AgentMessage(
            message_type="error",
            sender="payment_ai_agent",
            intent="payment_failed",
            conversation_id=message.conversation_id,
            payload={"error": error_msg}
        ).model_dump()

# Legacy endpoint for backward compatibility
@app.post("/handlePayment")
async def handle_payment_legacy(intent: Dict):
    """Legacy endpoint that forwards to A2A endpoint"""
    message = AgentMessage(
        message_type="request",
        sender="legacy_client",
        intent="process_payment",
        payload=intent
    )
    return await process_payment(message)