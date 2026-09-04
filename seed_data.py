from datetime import datetime, timedelta

from db import get_session, initialize_database
from models import (
    Customer, PurchaseOrder, OrderLineItem, GoodsReceivedNote, Invoice,
    BankRemittance, PaymentApplication, DunningAction, CaseEvidence,
    HumanReviewCase, AgentAction,
    PurchaseOrderStatus, OrderLineItemStatus, GRNStatus, InvoiceQAStatus,
    InvoiceStatus, RemittanceStatus, DunningActionStatus, AgentActionStatus
)

now = datetime.utcnow()

def add_customer(s, customer_id, name, credit=100000):
    s.add(Customer(
        customer_id=customer_id,
        company_name=name,
        billing_email=f"billing{customer_id}@example.com",
        contact_email=f"finance{customer_id}@example.com",
        credit_limit=credit
    ))

def add_case_invoice(
    s, po_id, grn_id, invoice_id, customer_id, total,
    issue_days_ago, due_days_offset,
    invoice_status=InvoiceStatus.OUTSTANDING,
    qa_status=InvoiceQAStatus.MATCH
):
    po = PurchaseOrder(
        po_id=po_id,
        customer_id=customer_id,
        order_date=now - timedelta(days=issue_days_ago + 10),
        expected_total=total,
        status=PurchaseOrderStatus.FULFILLED
    )
    grn = GoodsReceivedNote(
        grn_id=grn_id,
        po_id=po_id,
        delivery_date=now - timedelta(days=issue_days_ago + 3),
        received_by_signature="Warehouse Receiver",
        status=GRNStatus.FULL_DELIVERY
    )
    invoice = Invoice(
        invoice_id=invoice_id,
        po_id=po_id,
        grn_id=grn_id,
        issue_date=now - timedelta(days=issue_days_ago),
        due_date=now + timedelta(days=due_days_offset),
        total_amount=total,
        qa_status=qa_status,
        status=invoice_status
    )
    s.add_all([po, grn, invoice])
    return invoice

def add_review(s, review_type, entity_type, entity_id, reason, recommendation):
    s.add(HumanReviewCase(
        review_type=review_type,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        recommended_action=recommendation,
        status="OPEN"
    ))

def add_agent_action(s, agent, entity_type, entity_id, action, decision, reason, confidence, status):
    s.add(AgentAction(
        agent_name=agent,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        decision=decision,
        reason=reason,
        confidence=confidence,
        status=status
    ))

def seed():
    initialize_database()
    s = get_session()
    try:
        s.query(PaymentApplication).delete()
        s.query(HumanReviewCase).delete()
        s.query(AgentAction).delete()
        s.query(DunningAction).delete()
        s.query(CaseEvidence).delete()
        s.query(BankRemittance).delete()
        s.query(Invoice).delete()
        s.query(GoodsReceivedNote).delete()
        s.query(OrderLineItem).delete()
        s.query(PurchaseOrder).delete()
        s.query(Customer).delete()

        # CUSTOMERS
        add_customer(s, 101, "ACME Corporation", 100000)
        add_customer(s, 102, "Globex Ltd", 80000)
        add_customer(s, 103, "Initech", 120000)
        add_customer(s, 104, "Umbrella Retail", 90000)
        add_customer(s, 105, "Stark Industries", 150000)
        add_customer(s, 106, "Wayne Enterprises", 200000)
        add_customer(s, 107, "Live Invoice Ltd", 100000)
        add_customer(s, 108, "Live Cash Ltd", 100000)
        add_customer(s, 109, "Live Collections Ltd", 100000)

        # -----------------------------------------------------
        # INVOICE QA: 3 genuine human-review cases
        # -----------------------------------------------------
        add_case_invoice(
            s, "PO-1001", "GRN-1001", "INV-1001", 101, 26000, 5, 25,
            qa_status=InvoiceQAStatus.MISMATCH
        )
        s.add_all([
            OrderLineItem(
                po_id="PO-1001", item_desc="Laptop", unit_price=1000,
                ordered_qty=20, received_qty=20, billed_qty=20,
                status=OrderLineItemStatus.SHIPPED
            ),
            OrderLineItem(
                po_id="PO-1001", item_desc="Monitor", unit_price=500,
                ordered_qty=10, received_qty=10, billed_qty=12,
                status=OrderLineItemStatus.MISMATCH_FLAGGED
            )
        ])
        s.add(CaseEvidence(
            entity_type="Invoice", entity_id="INV-1001",
            source_system="EMAIL", source="Supplier",
            evidence_type="SUPPLIER_NOTE",
            content="Supplier states two extra monitors were requested, but no customer approval is attached."
        ))
        add_review(
            s, "INVOICE_QA_REVIEW", "Invoice", "INV-1001",
            "Invoice bills 12 monitors while PO and GRN support only 10.",
            "Verify whether the two extra monitors were authorised."
        )
        add_agent_action(
            s, "Invoice QA Agent", "Invoice", "INV-1001",
            "3-way match review", "HUMAN_REVIEW",
            "Quantity mismatch remains unresolved.", 0.91,
            AgentActionStatus.HUMAN_REVIEW
        )

        add_case_invoice(
            s, "PO-1003", "GRN-1003", "INV-1003", 104, 18000, 6, 24,
            qa_status=InvoiceQAStatus.MISMATCH
        )
        s.add(OrderLineItem(
            po_id="PO-1003", item_desc="Office Chair", unit_price=300,
            ordered_qty=60, received_qty=55, billed_qty=60,
            status=OrderLineItemStatus.MISMATCH_FLAGGED
        ))
        s.add(CaseEvidence(
            entity_type="Invoice", entity_id="INV-1003",
            source_system="WAREHOUSE_SYSTEM", source="Warehouse",
            evidence_type="SHORT_SHIPMENT_NOTE",
            content="Warehouse confirms only 55 of 60 chairs were received."
        ))
        add_review(
            s, "INVOICE_QA_REVIEW", "Invoice", "INV-1003",
            "Supplier billed 60 chairs but warehouse received only 55.",
            "Confirm whether the remaining 5 units are still due before approving."
        )
        add_agent_action(
            s, "Invoice QA Agent", "Invoice", "INV-1003",
            "3-way match review", "HUMAN_REVIEW",
            "Short-shipment evidence conflicts with billed quantity.", 0.94,
            AgentActionStatus.HUMAN_REVIEW
        )

        add_case_invoice(
            s, "PO-1004", "GRN-1004", "INV-1004", 105, 31500, 3, 27,
            qa_status=InvoiceQAStatus.MISMATCH
        )
        s.add(OrderLineItem(
            po_id="PO-1004", item_desc="Network Switch", unit_price=1500,
            ordered_qty=20, received_qty=20, billed_qty=21,
            status=OrderLineItemStatus.MISMATCH_FLAGGED
        ))
        s.add(CaseEvidence(
            entity_type="Invoice", entity_id="INV-1004",
            source_system="CRM", source="Account Management",
            evidence_type="ACCOUNT_NOTE",
            content="Customer discussed one additional switch, but written approval cannot be located."
        ))
        add_review(
            s, "INVOICE_QA_REVIEW", "Invoice", "INV-1004",
            "Invoice includes one more network switch than the approved PO quantity.",
            "Locate written approval for the additional unit."
        )
        add_agent_action(
            s, "Invoice QA Agent", "Invoice", "INV-1004",
            "3-way match review", "HUMAN_REVIEW",
            "Possible approved change exists but documentary evidence is incomplete.", 0.82,
            AgentActionStatus.HUMAN_REVIEW
        )

        # Invoice QA automated clean match
        inv1002 = add_case_invoice(
            s, "PO-1002", "GRN-1002", "INV-1002", 102, 12000, 4, 26
        )
        s.add(OrderLineItem(
            po_id="PO-1002", item_desc="Server Rack", unit_price=3000,
            ordered_qty=4, received_qty=4, billed_qty=4,
            status=OrderLineItemStatus.SHIPPED
        ))
        add_agent_action(
            s, "Invoice QA Agent", "Invoice", "INV-1002",
            "3-way match review", "ACCEPT",
            "PO, GRN and invoice quantities and values match.", 1.0,
            AgentActionStatus.COMPLETED
        )

        # -----------------------------------------------------
        # CASH APPLICATION: genuinely ambiguous human reviews
        # -----------------------------------------------------
        add_case_invoice(s, "PO-2001", "GRN-2001", "INV-2001", 101, 25000, 30, 0)
        add_case_invoice(s, "PO-2002", "GRN-2002", "INV-2002", 101, 25000, 25, 5)

        s.add(BankRemittance(
            payment_id="PAY-2001", payment_date=now,
            amount_received=25000,
            raw_bank_text="ACME Corporation September payment",
            status=RemittanceStatus.UNMATCHED_ESCALATED,
            matched_invoice_id=None
        ))
        add_review(
            s, "CASH_APPLICATION_REVIEW", "BankRemittance", "PAY-2001",
            "Payment amount matches two outstanding ACME invoices and the bank text does not identify which one.",
            "Select the intended invoice manually."
        )
        add_agent_action(
            s, "Cash Application Agent", "BankRemittance", "PAY-2001",
            "payment matching", "HUMAN_REVIEW",
            "Two ACME invoices have the same remaining balance, so the payment cannot be uniquely matched.", 0.40,
            AgentActionStatus.HUMAN_REVIEW
        )

        add_case_invoice(s, "PO-2003", "GRN-2003", "INV-2003", 104, 16000, 35, -5)
        add_case_invoice(s, "PO-2004", "GRN-2004", "INV-2004", 104, 15800, 33, -3)

        s.add(BankRemittance(
            payment_id="PAY-2003", payment_date=now - timedelta(days=1),
            amount_received=15900,
            raw_bank_text="Umbrella Retail August settlement",
            status=RemittanceStatus.UNMATCHED_ESCALATED,
            matched_invoice_id=None
        ))
        add_review(
            s, "CASH_APPLICATION_REVIEW", "BankRemittance", "PAY-2003",
            "Payment is close to two Umbrella invoices but exactly matches neither balance.",
            "Review whether deductions, fees or an incorrect payment amount explain the difference."
        )
        add_agent_action(
            s, "Cash Application Agent", "BankRemittance", "PAY-2003",
            "payment matching", "HUMAN_REVIEW",
            "No exact invoice or unique exact combination reconciles to the payment.", 0.46,
            AgentActionStatus.HUMAN_REVIEW
        )

        # -----------------------------------------------------
        # CASH APPLICATION: automated exact single match
        # -----------------------------------------------------
        s.add(BankRemittance(
            payment_id="PAY-2002", payment_date=now - timedelta(days=1),
            amount_received=12000,
            raw_bank_text="GLOBEX LTD PAYMENT REF INV-1002",
            status=RemittanceStatus.MATCHED_AUTO,
            matched_invoice_id="INV-1002"
        ))
        s.add(PaymentApplication(
            payment_id="PAY-2002", invoice_id="INV-1002",
            matched_amount=12000, match_confidence=1.0,
            status="MATCHED_AUTO"
        ))
        inv1002.status = InvoiceStatus.PAID
        add_agent_action(
            s, "Cash Application Agent", "BankRemittance", "PAY-2002",
            "payment matching", "MATCH",
            "Exact invoice reference and amount matched INV-1002.", 1.0,
            AgentActionStatus.COMPLETED
        )

        # -----------------------------------------------------
        # CASH APPLICATION: automated unique split match
        # -----------------------------------------------------
        inv2005 = add_case_invoice(
            s, "PO-2005", "GRN-2005", "INV-2005", 106, 9800, 20, 10,
            invoice_status=InvoiceStatus.PAID
        )
        inv2006 = add_case_invoice(
            s, "PO-2006", "GRN-2006", "INV-2006", 106, 10200, 18, 12,
            invoice_status=InvoiceStatus.PAID
        )

        s.add(BankRemittance(
            payment_id="PAY-2004", payment_date=now - timedelta(hours=3),
            amount_received=20000,
            raw_bank_text="WAYNE ENTERPRISES consolidated payment",
            status=RemittanceStatus.MATCHED_AUTO,
            matched_invoice_id=None
        ))
        s.add_all([
            PaymentApplication(
                payment_id="PAY-2004", invoice_id="INV-2005",
                matched_amount=9800, match_confidence=1.0,
                status="MATCHED_AUTO"
            ),
            PaymentApplication(
                payment_id="PAY-2004", invoice_id="INV-2006",
                matched_amount=10200, match_confidence=1.0,
                status="MATCHED_AUTO"
            )
        ])
        add_agent_action(
            s, "Cash Application Agent", "BankRemittance", "PAY-2004",
            "payment matching", "MATCH",
            "Wayne Enterprises was identified in the remittance and INV-2005 plus INV-2006 are the unique outstanding invoice combination totalling £20,000.", 1.0,
            AgentActionStatus.COMPLETED
        )

        # -----------------------------------------------------
        # DUNNING: 3 genuine human-review cases
        # -----------------------------------------------------
        add_case_invoice(
            s, "PO-3001", "GRN-3001", "INV-3001", 103, 42000, 95, -65,
            invoice_status=InvoiceStatus.OVERDUE
        )
        s.add_all([
            DunningAction(
                invoice_id="INV-3001", customer_id=103,
                action_date=now - timedelta(days=35),
                action_type="REMINDER",
                message="First payment reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3001", customer_id=103,
                action_date=now - timedelta(days=15),
                action_type="REMINDER",
                message="Second reminder sent after missed promise.",
                status=DunningActionStatus.SENT
            ),
            CaseEvidence(
                entity_type="Invoice", entity_id="INV-3001",
                source_system="CRM", source="Collections",
                evidence_type="PAYMENT_HISTORY",
                content="Customer promised payment twice but both dates were missed."
            ),
            CaseEvidence(
                entity_type="Customer", entity_id="103",
                source_system="CRM", source="Account Management",
                evidence_type="CUSTOMER_HISTORY",
                content="Customer has become increasingly difficult to contact."
            )
        ])
        add_review(
            s, "DUNNING_REVIEW", "Invoice", "INV-3001",
            "Invoice is 65 days overdue with two broken payment promises.",
            "Escalate for manual collections review."
        )
        add_agent_action(
            s, "Dunning Agent", "Invoice", "INV-3001",
            "collections assessment", "HUMAN_REVIEW",
            "High-value overdue invoice with repeated broken promises.", 0.90,
            AgentActionStatus.HUMAN_REVIEW
        )

        add_case_invoice(
            s, "PO-3003", "GRN-3003", "INV-3003", 105, 27500, 80, -50,
            invoice_status=InvoiceStatus.OVERDUE
        )
        s.add_all([
            DunningAction(
                invoice_id="INV-3003", customer_id=105,
                action_date=now - timedelta(days=20),
                action_type="REMINDER",
                message="Payment reminder sent.",
                status=DunningActionStatus.SENT
            ),
            CaseEvidence(
                entity_type="Invoice", entity_id="INV-3003",
                source_system="EMAIL", source="Customer",
                evidence_type="CUSTOMER_RESPONSE",
                content="Customer disputes a delivery charge but has not opened a formal dispute case."
            )
        ])
        add_review(
            s, "DUNNING_REVIEW", "Invoice", "INV-3003",
            "Invoice is 50 days overdue and customer has raised an informal billing concern.",
            "Review the delivery charge before sending further automated reminders."
        )
        add_agent_action(
            s, "Dunning Agent", "Invoice", "INV-3003",
            "collections assessment", "HUMAN_REVIEW",
            "Potential dispute makes further automated chasing risky.", 0.88,
            AgentActionStatus.HUMAN_REVIEW
        )

        add_case_invoice(
            s, "PO-3004", "GRN-3004", "INV-3004", 106, 68000, 110, -80,
            invoice_status=InvoiceStatus.OVERDUE
        )
        s.add_all([
            DunningAction(
                invoice_id="INV-3004", customer_id=106,
                action_date=now - timedelta(days=45),
                action_type="REMINDER",
                message="Initial reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3004", customer_id=106,
                action_date=now - timedelta(days=25),
                action_type="REMINDER",
                message="Second reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3004", customer_id=106,
                action_date=now - timedelta(days=10),
                action_type="REMINDER",
                message="Final automated reminder sent.",
                status=DunningActionStatus.SENT
            ),
            CaseEvidence(
                entity_type="Invoice", entity_id="INV-3004",
                source_system="CRM", source="Collections",
                evidence_type="COLLECTION_NOTE",
                content="No response has been received after three reminders."
            )
        ])
        add_review(
            s, "DUNNING_REVIEW", "Invoice", "INV-3004",
            "£68,000 invoice is 80 days overdue with no response after three reminders.",
            "Escalate to senior collections or account management."
        )
        add_agent_action(
            s, "Dunning Agent", "Invoice", "INV-3004",
            "collections assessment", "HUMAN_REVIEW",
            "Large exposure and prolonged non-response require escalation.", 0.96,
            AgentActionStatus.HUMAN_REVIEW
        )

        # Dunning automated WAIT
        add_case_invoice(
            s, "PO-3002", "GRN-3002", "INV-3002", 102, 8500, 48, -18,
            invoice_status=InvoiceStatus.OVERDUE
        )
        s.add(CaseEvidence(
            entity_type="Invoice", entity_id="INV-3002",
            source_system="EMAIL", source="Customer",
            evidence_type="PAYMENT_PROMISE",
            content="Customer confirmed payment is approved internally and scheduled for Friday."
        ))
        add_agent_action(
            s, "Dunning Agent", "Invoice", "INV-3002",
            "collections assessment", "WAIT",
            "Recent credible payment promise indicates payment is imminent.", 0.90,
            AgentActionStatus.COMPLETED
        )
        # =====================================================
        # LIVE AGENT CASES
        # These contain ERP input only.
        # No AgentAction / HumanReviewCase is seeded.
        # =====================================================

        # -----------------------------------------------------
        # LIVE 1: Invoice QA
        # Deliberate quantity discrepancy.
        # Running the Invoice QA agent should detect the
        # mismatch and use AI to interpret the exception.
        # -----------------------------------------------------

        add_case_invoice(
            s,
            "PO-LIVE-001",
            "GRN-LIVE-001",
            "INV-LIVE-001",
            107,
            11000,
            5,
            25,
            qa_status=InvoiceQAStatus.PENDING
        )

        s.add(
            OrderLineItem(
                po_id="PO-LIVE-001",
                item_desc="Business Laptop",
                unit_price=1000,
                ordered_qty=10,
                received_qty=10,
                billed_qty=11,
                status=OrderLineItemStatus.MISMATCH_FLAGGED
            )
        )

        s.add(
            CaseEvidence(
                entity_type="Invoice",
                entity_id="INV-LIVE-001",
                source_system="EMAIL",
                source="Supplier",
                evidence_type="SUPPLIER_NOTE",
                content=(
                    "Supplier states that an additional laptop was requested "
                    "verbally, but no written approval is available."
                )
            )
        )
        # -----------------------------------------------------
        # LIVE 2: Cash Application
        #
        # Payment = £10,000
        #
        # INV-LIVE-101 = £7,000
        # INV-LIVE-102 = £3,000
        #
        # There is exactly one combination for Live Cash Ltd
        # that totals the remittance.
        # -----------------------------------------------------

        add_case_invoice(
            s,
            "PO-LIVE-101",
            "GRN-LIVE-101",
            "INV-LIVE-101",
            108,
            7000,
            20,
            10
        )

        add_case_invoice(
            s,
            "PO-LIVE-102",
            "GRN-LIVE-102",
            "INV-LIVE-102",
            108,
            3000,
            18,
            12
        )

        s.add(
            BankRemittance(
                payment_id="PAY-LIVE-001",
                payment_date=now,
                amount_received=10000,
                raw_bank_text="LIVE CASH LTD consolidated payment",
                status=RemittanceStatus.UNPROCESSED,
                matched_invoice_id=None
            )
        )
        # -----------------------------------------------------
        # LIVE 3: Dunning
        # Overdue invoice with contextual evidence.
        # -----------------------------------------------------

        add_case_invoice(
            s,
            "PO-LIVE-201",
            "GRN-LIVE-201",
            "INV-LIVE-002",
            109,
            24000,
            70,
            -40,
            invoice_status=InvoiceStatus.OVERDUE
        )

        s.add(
            DunningAction(
                invoice_id="INV-LIVE-002",
                customer_id=109,
                action_date=now - timedelta(days=15),
                action_type="REMINDER",
                message="Initial payment reminder sent.",
                status=DunningActionStatus.SENT
            )
        )

        s.add(
            CaseEvidence(
                entity_type="Invoice",
                entity_id="INV-LIVE-002",
                source_system="EMAIL",
                source="Customer",
                evidence_type="PAYMENT_PROMISE",
                content=(
                    "Customer acknowledged the overdue balance and said "
                    "payment is awaiting final internal approval."
                )
            )
        )
        s.commit()
        print("Demo data seeded successfully.")
        print("Open reviews: Invoice QA=3, Cash Application=2, Dunning=3")
        print("Automated cash examples: PAY-2002 single match, PAY-2004 split match")

    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

if __name__ == "__main__":
    seed()
