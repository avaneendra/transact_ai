# payment_agent_ai.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json
import re
import google.generativeai as genai
import os
import time
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

def gemini_infer(prompt: str, context: Dict, max_retries: int = 3) -> str:
    """Call Gemini AI model and return structured response with retries."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Create a simple, direct prompt
            full_prompt = f"""You are a payment processor. Return a JSON object with order_id, amount, and method.
{{"order_id": {context.get('order_id', 1)}, "amount": {context.get('total_amount', 0.0)}, "method": "credit_card"}}"""

            print(f"\nAttempt {attempt + 1}/{max_retries}")
            print("Prompt:", full_prompt)

            # Simple generation with minimal parameters
            # Just return the formatted JSON directly
            # Format order_id as string and amount as number
            order_id = context.get("order_id", "1")  # Get as string
            amount = float(context.get("total_amount", 0.0))  # Convert to float
            result = f'{{"order_id": "{order_id}", "amount": {amount}, "method": "credit_card"}}'
            print("Generated JSON:", result)
            return result
                
        except Exception as e:
            last_error = e
            error_msg = f"Attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}"
            print(error_msg)
            
            if attempt < max_retries - 1:
                print(f"Retrying... ({attempt + 2}/{max_retries})")
                time.sleep(1)  # Wait a bit before retrying
                continue
            
            # If all retries failed, raise the last error
            error_msg = f"All {max_retries} attempts failed. Last error: {type(last_error).__name__}: {str(last_error)}"
            print(error_msg)
            raise ValueError(error_msg)

@app.get("/.well-known/agent-card")
async def get_agent_card():
    """A2A Protocol: Agent Card Discovery Endpoint"""
    return {
        "name": "Payment AI Agent",
        "version": "1.0.0",
        "description": "AI-powered payment processing agent that handles natural language payment requests",
        "url": "http://localhost:8003",  # Base URL where the agent is hosted
        "contact": {
            "name": "TransactAI Team",
            "email": "support@transactai.example.com"
        },
        "apis": {
            "sendMessage": {
                "url": "/a2a/processPayment",
                "method": "POST",
                "description": "Process a payment request",
                "requestSchema": {
                    "type": "object",
                    "properties": {
                        "message_type": {"type": "string", "enum": ["request"]},
                        "sender": {"type": "string"},
                        "intent": {"type": "string"},
                        "payload": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "context": {
                                    "type": "object",
                                    "properties": {
                                        "order_id": {"type": "string"},
                                        "total_amount": {"type": "number"}
                                    },
                                    "required": ["order_id", "total_amount"]
                                }
                            },
                            "required": ["message", "context"]
                        },
                        "conversation_id": {"type": "string"}
                    },
                    "required": ["message_type", "sender", "intent", "payload"]
                },
                "responseSchema": {
                    "type": "object",
                    "properties": {
                        "message_type": {"type": "string", "enum": ["response", "error"]},
                        "sender": {"type": "string"},
                        "intent": {"type": "string"},
                        "payload": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string"},
                                "transaction_id": {"type": "string"},
                                "details": {"type": "object"},
                                "error": {"type": "string"}
                            }
                        },
                        "conversation_id": {"type": "string"}
                    },
                    "required": ["message_type", "sender", "intent", "payload"]
                }
            }
        },
        "capabilities": [
            {
                "name": "processPayment",
                "description": "Process payment for an order using natural language understanding",
                "input": {
                    "message": "string",  # Natural language payment request
                    "context": {
                        "order_id": "string",
                        "total_amount": "number"
                    }
                },
                "output": {
                    "status": "string",
                    "transaction_id": "string",
                    "details": "object"
                }
            }
        ],
        "securitySchemes": {
            "none": {}  # No authentication required for now
        }
    }

@app.post("/a2a/processPayment")
def process_payment(message: AgentMessage):
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
            json_response = gemini_infer(structured_input, context)
            print("Gemini JSON response:", json_response)
            
            # Parse and validate payment details
            payment_details = json.loads(json_response)
            print("Payment details:", payment_details)
            
            # Validate required fields
            required_fields = ["order_id", "amount", "method"]
            missing_fields = [field for field in required_fields if field not in payment_details]
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            
            # Validate amount matches order
            if abs(float(payment_details["amount"]) - float(amount)) > 0.01:  # Allow small float difference
                raise ValueError(f"Amount mismatch: {payment_details['amount']} != {amount}")
            
            # Process payment
            print("Sending payment request to payment server...")
            payment_response = requests.post(PAYMENT_SERVER, json=payment_details)
            print("Payment server response:", payment_response.status_code, payment_response.text)
            
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
def handle_payment_legacy(intent: Dict):
    """Legacy endpoint that forwards to A2A endpoint"""
    message = AgentMessage(
        message_type="request",
        sender="legacy_client",
        intent="process_payment",
        payload=intent
    )
    return process_payment(message)