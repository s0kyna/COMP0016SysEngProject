# Orchestration Loop

# main.py
import db
from agents.planner import get_next_job
from agents.invoice_qa import analyze_invoice_qa
from agents.supervisor import enforce_rules

def run_pipeline():
    print("--- Starting O2C Pipeline ---")
    
    # 1. Planner fetches job
    job = get_next_job(db)
    print(f"[Planner] Processing PO: {job['po']['po_number']}")
    
    # 2. AI QA Agent inspects mismatch
    qa_result = analyze_invoice_qa(job['po'], job['invoice'])
    print(f"[Invoice QA Agent] Status: {qa_result['status']}")
    print(f"[Invoice QA Agent] Findings: {qa_result['findings']}")
    
    # 3. Supervisor enforces rule safety
    decision = enforce_rules(job['invoice']['total'], qa_result['status'])
    print(f"[Supervisor] Final Decision: {decision['action']} ({decision['reason']})")
    
    return decision

if __name__ == "__main__":
    run_pipeline()