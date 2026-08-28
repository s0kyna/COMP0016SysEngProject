# agents/invoice_qa.py
import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "mock-key"))

def analyze_invoice_qa(po: dict, invoice: dict) -> dict:
    """Uses LLM to evaluate fuzzy matching between PO and Invoice."""
    
    # Fallback mock response for testing without API keys
    if os.environ.get("OPENAI_API_KEY") is None:
        return {
            "status": "MISMATCH_DETECTED",
            "findings": "Item description mismatch ('Industrial Widget V2' vs 'Ind. Widget Type B') and price mismatch ($50 vs $55).",
            "draft_email": "Dear Acme Corp, We noticed a pricing discrepancy on INV-8088..."
        }

    prompt = f"""
    Compare this PO and Invoice for discrepancies.
    PO: {json.dumps(po)}
    Invoice: {json.dumps(invoice)}
    
    Respond strictly in JSON format with keys: "status" ("MATCH" or "MISMATCH_DETECTED"), "findings", "draft_email".
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)