# agents/supervisor.py
APPROVAL_THRESHOLD = 500.00

def enforce_rules(amount: float, qa_status: str) -> dict:
    if qa_status == "MISMATCH_DETECTED":
        return {"action": "REJECT", "reason": "Discrepancy found by QA Agent."}
    if amount > APPROVAL_THRESHOLD:
        return {"action": "ESCALATE", "reason": f"Amount {amount} exceeds threshold {APPROVAL_THRESHOLD}"}
    return {"action": "APPROVE", "reason": "All checks passed."}