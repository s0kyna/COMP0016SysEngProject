from datetime import datetime, timedelta
from db import get_session, initialize_database
from models import (
    Customer, PurchaseOrder, OrderLineItem, GoodsReceivedNote, Invoice,
    BankRemittance, DunningAction, CaseEvidence, HumanReviewCase, AgentAction,
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

def add_po_grn_invoice(
    s, po_id, grn_id, invoice_id, customer_id, total,
    issue_days_ago, due_days_offset, invoice_status=InvoiceStatus.OUTSTANDING,
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
    return po, grn, invoice

def seed():
    initialize_database()
    s = get_session()

    try:
        # ---------------------------------------------------------
        # CLEAR DEMO DATA
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # CUSTOMERS
        # ---------------------------------------------------------
        add_customer(s, 101, "ACME Corporation", 100000)
        add_customer(s, 102, "Globex Ltd", 80000)
        add_customer(s, 103, "Initech", 120000)
        add_customer(s, 104, "Umbrella Retail", 90000)
        add_customer(s, 105, "Stark Industries", 150000)
        add_customer(s, 106, "Wayne Enterprises", 200000)

        # =========================================================
        # INVOICE QA OPEN REVIEW 1
        # =========================================================
        po, grn, inv = add_po_grn_invoice(
            s, "PO-1001", "GRN-1001", "INV-1001",
            101, 26000, 5, 25,
            qa_status=InvoiceQAStatus.MISMATCH
        )

        s.add_all([
            OrderLineItem(
                po_id="PO-1001",
                item_desc="Laptop",
                unit_price=1000,
                ordered_qty=20,
                received_qty=20,
                billed_qty=20,
                status=OrderLineItemStatus.SHIPPED
            ),
            OrderLineItem(
                po_id="PO-1001",
                item_desc="Monitor",
                unit_price=500,
                ordered_qty=10,
                received_qty=10,
                billed_qty=12,
                status=OrderLineItemStatus.MISMATCH_FLAGGED
            )
        ])

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-1001",
            source_system="EMAIL",
            source="Supplier",
            evidence_type="SUPPLIER_NOTE",
            content="Supplier states two extra monitors were requested, but no customer approval is attached."
        ))

        s.add(HumanReviewCase(
            review_type="INVOICE_QA_REVIEW",
            entity_type="Invoice",
            entity_id="INV-1001",
            reason="Invoice bills 12 monitors while PO and GRN support only 10.",
            recommended_action="Verify whether the two extra monitors were authorised.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Invoice QA Agent",
            entity_type="Invoice",
            entity_id="INV-1001",
            action="3-way match review",
            decision="HUMAN_REVIEW",
            reason="Quantity mismatch remains unresolved.",
            confidence=0.91,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # INVOICE QA OPEN REVIEW 2
        # =========================================================
        add_po_grn_invoice(
            s, "PO-1003", "GRN-1003", "INV-1003",
            104, 18000, 6, 24,
            qa_status=InvoiceQAStatus.MISMATCH
        )

        s.add(OrderLineItem(
            po_id="PO-1003",
            item_desc="Office Chair",
            unit_price=300,
            ordered_qty=60,
            received_qty=55,
            billed_qty=60,
            status=OrderLineItemStatus.MISMATCH_FLAGGED
        ))

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-1003",
            source_system="WAREHOUSE_SYSTEM",
            source="Warehouse",
            evidence_type="SHORT_SHIPMENT_NOTE",
            content="Warehouse confirms only 55 of 60 chairs were received."
        ))

        s.add(HumanReviewCase(
            review_type="INVOICE_QA_REVIEW",
            entity_type="Invoice",
            entity_id="INV-1003",
            reason="Supplier billed 60 chairs but warehouse received only 55.",
            recommended_action="Confirm whether the remaining 5 units are still due before approving.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Invoice QA Agent",
            entity_type="Invoice",
            entity_id="INV-1003",
            action="3-way match review",
            decision="HUMAN_REVIEW",
            reason="Short-shipment evidence conflicts with billed quantity.",
            confidence=0.94,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # INVOICE QA OPEN REVIEW 3
        # =========================================================
        add_po_grn_invoice(
            s, "PO-1004", "GRN-1004", "INV-1004",
            105, 31500, 3, 27,
            qa_status=InvoiceQAStatus.MISMATCH
        )

        s.add(OrderLineItem(
            po_id="PO-1004",
            item_desc="Network Switch",
            unit_price=1500,
            ordered_qty=20,
            received_qty=20,
            billed_qty=21,
            status=OrderLineItemStatus.MISMATCH_FLAGGED
        ))

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-1004",
            source_system="CRM",
            source="Account Management",
            evidence_type="ACCOUNT_NOTE",
            content="Customer discussed one additional switch, but written approval cannot be located."
        ))

        s.add(HumanReviewCase(
            review_type="INVOICE_QA_REVIEW",
            entity_type="Invoice",
            entity_id="INV-1004",
            reason="Invoice includes one more network switch than the approved PO quantity.",
            recommended_action="Locate written approval for the additional unit.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Invoice QA Agent",
            entity_type="Invoice",
            entity_id="INV-1004",
            action="3-way match review",
            decision="HUMAN_REVIEW",
            reason="Possible approved change exists but documentary evidence is incomplete.",
            confidence=0.82,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # INVOICE QA AUTO CASE
        # =========================================================
        add_po_grn_invoice(
            s, "PO-1002", "GRN-1002", "INV-1002",
            102, 12000, 4, 26,
            qa_status=InvoiceQAStatus.MATCH
        )

        s.add(OrderLineItem(
            po_id="PO-1002",
            item_desc="Server Rack",
            unit_price=3000,
            ordered_qty=4,
            received_qty=4,
            billed_qty=4,
            status=OrderLineItemStatus.SHIPPED
        ))

        s.add(AgentAction(
            agent_name="Invoice QA Agent",
            entity_type="Invoice",
            entity_id="INV-1002",
            action="3-way match review",
            decision="ACCEPT",
            reason="PO, GRN and invoice quantities and values match.",
            confidence=1.0,
            status=AgentActionStatus.COMPLETED
        ))

        # =========================================================
        # CASH APPLICATION OPEN REVIEW 1
        # =========================================================
        add_po_grn_invoice(
            s, "PO-2001", "GRN-2001", "INV-2001",
            101, 25000, 30, 0
        )
        add_po_grn_invoice(
            s, "PO-2002", "GRN-2002", "INV-2002",
            101, 25000, 25, 5
        )

        s.add(BankRemittance(
            payment_id="PAY-2001",
            payment_date=now,
            amount_received=25000,
            raw_bank_text="ACME September payment",
            status=RemittanceStatus.UNMATCHED_ESCALATED,
            matched_invoice_id=None
        ))

        s.add(HumanReviewCase(
            review_type="CASH_APPLICATION_REVIEW",
            entity_type="BankRemittance",
            entity_id="PAY-2001",
            reason="Payment amount matches multiple outstanding ACME invoices.",
            recommended_action="Select the intended invoice manually.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id="PAY-2001",
            action="payment matching",
            decision="HUMAN_REVIEW",
            reason="Two invoices are equally plausible candidates.",
            confidence=0.40,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # CASH APPLICATION OPEN REVIEW 2
        # =========================================================
        add_po_grn_invoice(
            s, "PO-2003", "GRN-2003", "INV-2003",
            104, 16000, 35, -5
        )
        add_po_grn_invoice(
            s, "PO-2004", "GRN-2004", "INV-2004",
            104, 15800, 33, -3
        )

        s.add(BankRemittance(
            payment_id="PAY-2003",
            payment_date=now - timedelta(days=1),
            amount_received=15900,
            raw_bank_text="UMBRELLA settlement August",
            status=RemittanceStatus.UNMATCHED_ESCALATED,
            matched_invoice_id=None
        ))

        s.add(HumanReviewCase(
            review_type="CASH_APPLICATION_REVIEW",
            entity_type="BankRemittance",
            entity_id="PAY-2003",
            reason="Payment value is close to two Umbrella invoices but exactly matches neither.",
            recommended_action="Review whether deductions or fees explain the difference.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id="PAY-2003",
            action="payment matching",
            decision="HUMAN_REVIEW",
            reason="No exact amount or invoice reference is available.",
            confidence=0.46,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # CASH APPLICATION OPEN REVIEW 3
        # =========================================================
        add_po_grn_invoice(
            s, "PO-2005", "GRN-2005", "INV-2005",
            106, 9800, 20, 10
        )
        add_po_grn_invoice(
            s, "PO-2006", "GRN-2006", "INV-2006",
            106, 10200, 18, 12
        )

        s.add(BankRemittance(
            payment_id="PAY-2004",
            payment_date=now - timedelta(days=2),
            amount_received=20000,
            raw_bank_text="WAYNE ENTERPRISES consolidated payment",
            status=RemittanceStatus.UNMATCHED_ESCALATED,
            matched_invoice_id=None
        ))

        s.add(HumanReviewCase(
            review_type="CASH_APPLICATION_REVIEW",
            entity_type="BankRemittance",
            entity_id="PAY-2004",
            reason="Payment appears to cover multiple invoices rather than one single invoice.",
            recommended_action="Determine whether the payment should be split across INV-2005 and INV-2006.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id="PAY-2004",
            action="payment matching",
            decision="HUMAN_REVIEW",
            reason="Likely multi-invoice payment requires manual allocation.",
            confidence=0.61,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # CASH APPLICATION AUTO CASE
        # =========================================================
        s.add(BankRemittance(
            payment_id="PAY-2002",
            payment_date=now - timedelta(days=1),
            amount_received=12000,
            raw_bank_text="GLOBEX PAYMENT REF INV-1002",
            status=RemittanceStatus.MATCHED_AUTO,
            matched_invoice_id="INV-1002"
        ))

        s.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id="PAY-2002",
            action="payment matching",
            decision="MATCH",
            reason="Exact invoice reference and amount matched INV-1002.",
            confidence=1.0,
            status=AgentActionStatus.COMPLETED
        ))

        # =========================================================
        # DUNNING OPEN REVIEW 1
        # =========================================================
        add_po_grn_invoice(
            s, "PO-3001", "GRN-3001", "INV-3001",
            103, 42000, 95, -65,
            invoice_status=InvoiceStatus.OVERDUE
        )

        s.add_all([
            DunningAction(
                invoice_id="INV-3001",
                customer_id=103,
                action_date=now - timedelta(days=35),
                action_type="REMINDER",
                message="First payment reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3001",
                customer_id=103,
                action_date=now - timedelta(days=15),
                action_type="REMINDER",
                message="Second reminder sent after missed promise.",
                status=DunningActionStatus.SENT
            )
        ])

        s.add_all([
            CaseEvidence(
                entity_type="Invoice",
                entity_id="INV-3001",
                source_system="CRM",
                source="Collections",
                evidence_type="PAYMENT_HISTORY",
                content="Customer promised payment twice but both dates were missed."
            ),
            CaseEvidence(
                entity_type="Customer",
                entity_id="103",
                source_system="CRM",
                source="Account Management",
                evidence_type="CUSTOMER_HISTORY",
                content="Customer has become increasingly difficult to contact."
            )
        ])

        s.add(HumanReviewCase(
            review_type="DUNNING_REVIEW",
            entity_type="Invoice",
            entity_id="INV-3001",
            reason="Invoice is 65 days overdue with two broken payment promises.",
            recommended_action="Escalate for manual collections review.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Dunning Agent",
            entity_type="Invoice",
            entity_id="INV-3001",
            action="collections assessment",
            decision="HUMAN_REVIEW",
            reason="High-value overdue invoice with repeated broken promises.",
            confidence=0.90,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # DUNNING OPEN REVIEW 2
        # =========================================================
        add_po_grn_invoice(
            s, "PO-3003", "GRN-3003", "INV-3003",
            105, 27500, 80, -50,
            invoice_status=InvoiceStatus.OVERDUE
        )

        s.add(DunningAction(
            invoice_id="INV-3003",
            customer_id=105,
            action_date=now - timedelta(days=20),
            action_type="REMINDER",
            message="Payment reminder sent.",
            status=DunningActionStatus.SENT
        ))

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-3003",
            source_system="EMAIL",
            source="Customer",
            evidence_type="CUSTOMER_RESPONSE",
            content="Customer disputes a delivery charge but has not opened a formal dispute case."
        ))

        s.add(HumanReviewCase(
            review_type="DUNNING_REVIEW",
            entity_type="Invoice",
            entity_id="INV-3003",
            reason="Invoice is 50 days overdue and customer has raised an informal billing concern.",
            recommended_action="Review the delivery charge before sending further automated reminders.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Dunning Agent",
            entity_type="Invoice",
            entity_id="INV-3003",
            action="collections assessment",
            decision="HUMAN_REVIEW",
            reason="Potential dispute makes additional automated chasing risky.",
            confidence=0.88,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # DUNNING OPEN REVIEW 3
        # =========================================================
        add_po_grn_invoice(
            s, "PO-3004", "GRN-3004", "INV-3004",
            106, 68000, 110, -80,
            invoice_status=InvoiceStatus.OVERDUE
        )

        s.add_all([
            DunningAction(
                invoice_id="INV-3004",
                customer_id=106,
                action_date=now - timedelta(days=45),
                action_type="REMINDER",
                message="Initial reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3004",
                customer_id=106,
                action_date=now - timedelta(days=25),
                action_type="REMINDER",
                message="Second reminder sent.",
                status=DunningActionStatus.SENT
            ),
            DunningAction(
                invoice_id="INV-3004",
                customer_id=106,
                action_date=now - timedelta(days=10),
                action_type="REMINDER",
                message="Final automated reminder sent.",
                status=DunningActionStatus.SENT
            )
        ])

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-3004",
            source_system="CRM",
            source="Collections",
            evidence_type="COLLECTION_NOTE",
            content="No response has been received after three reminders."
        ))

        s.add(HumanReviewCase(
            review_type="DUNNING_REVIEW",
            entity_type="Invoice",
            entity_id="INV-3004",
            reason="£68,000 invoice is 80 days overdue with no response after three reminders.",
            recommended_action="Escalate to senior collections or account management.",
            status="OPEN"
        ))

        s.add(AgentAction(
            agent_name="Dunning Agent",
            entity_type="Invoice",
            entity_id="INV-3004",
            action="collections assessment",
            decision="HUMAN_REVIEW",
            reason="Large exposure and prolonged non-response require escalation.",
            confidence=0.96,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        # =========================================================
        # DUNNING AUTO WAIT
        # =========================================================
        add_po_grn_invoice(
            s, "PO-3002", "GRN-3002", "INV-3002",
            102, 8500, 48, -18,
            invoice_status=InvoiceStatus.OVERDUE
        )

        s.add(CaseEvidence(
            entity_type="Invoice",
            entity_id="INV-3002",
            source_system="EMAIL",
            source="Customer",
            evidence_type="PAYMENT_PROMISE",
            content="Customer confirmed payment is approved internally and scheduled for Friday."
        ))

        s.add(AgentAction(
            agent_name="Dunning Agent",
            entity_type="Invoice",
            entity_id="INV-3002",
            action="collections assessment",
            decision="WAIT",
            reason="Recent credible payment promise indicates payment is imminent.",
            confidence=0.90,
            status=AgentActionStatus.COMPLETED
        ))

        s.commit()
        print("Demo data seeded successfully.")
        print("Invoice QA open reviews: 3")
        print("Cash Application open reviews: 3")
        print("Dunning open reviews: 3")

    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

if __name__ == "__main__":
    seed()