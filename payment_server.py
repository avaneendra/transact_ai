# payment_server.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PaymentRequest(BaseModel):
    order_id: int
    amount: float
    method: str

@app.post("/createPayment")
async def create_payment(req: PaymentRequest):
    return {
        "status": "success",
        "order_id": req.order_id,
        "amount": req.amount,
        "method": req.method,
        "transaction_id": "txn_12345"
    }

