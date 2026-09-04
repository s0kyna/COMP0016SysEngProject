<script setup>
import { ref, computed, onMounted } from "vue"

const sections = [
  { label: "Overview", value: "OVERVIEW" },
  { label: "Invoice QA", value: "INVOICE_QA_REVIEW" },
  { label: "Cash Application", value: "CASH_APPLICATION_REVIEW" },
  { label: "Dunning", value: "DUNNING_REVIEW" },
  { label: "Agent Activity", value: "AGENT_ACTIVITY" },
  { label: "Case Overview", value: "CASE_OVERVIEW" }
]

const selectedSection = ref("OVERVIEW")
const reviews = ref([])
const allReviews = ref([])
const selectedReview = ref(null)
const loading = ref(false)
const error = ref("")
const cashDetails = ref(null)
const invoiceQaDetails = ref(null)
const dunningDetails = ref(null)
const cashAllocations = ref({})
const agentActions = ref([])
const caseId = ref("")
const caseOverview = ref(null)

const reviewSections = ["INVOICE_QA_REVIEW", "CASH_APPLICATION_REVIEW", "DUNNING_REVIEW"]
const currentTitle = computed(() => sections.find(x => x.value === selectedSection.value)?.label || "")
const openCount = computed(() => allReviews.value.length)
const allocatedTotal = computed(() => Object.values(cashAllocations.value).reduce((sum, value) => sum + (Number(value) || 0), 0))
const paymentRemaining = computed(() => cashDetails.value ? cashDetails.value.payment.amount - allocatedTotal.value : 0)

function countType(type) {
  return allReviews.value.filter(x => x.review_type === type).length
}

async function loadAllReviews() {
  const response = await fetch("http://127.0.0.1:8000/reviews")
  if (!response.ok) throw new Error("Could not load reviews")
  allReviews.value = await response.json()
}

async function loadSection(section) {
  selectedSection.value = section
  selectedReview.value = null
  cashDetails.value = null
  invoiceQaDetails.value = null
  dunningDetails.value = null
  cashAllocations.value = {}
  caseOverview.value = null
  error.value = ""
  if (reviewSections.includes(section)) await loadReviews()
  else if (section === "AGENT_ACTIVITY") await loadAgentActions()
  else if (section === "OVERVIEW") {
    await loadAllReviews()
    await loadAgentActions()
  }
}

async function loadReviews() {
  loading.value = true
  try {
    const response = await fetch(`http://127.0.0.1:8000/reviews?review_type=${selectedSection.value}`)
    if (!response.ok) throw new Error(`API returned ${response.status}`)
    reviews.value = await response.json()
  } catch (err) {
    console.error(err)
    error.value = "Could not connect to the O2C backend."
  } finally {
    loading.value = false
  }
}

async function openReview(id) {
  try {
    const response = await fetch(`http://127.0.0.1:8000/reviews/${id}`)
    if (!response.ok) throw new Error("Could not load review")
    selectedReview.value = await response.json()
    cashDetails.value = null
    invoiceQaDetails.value = null
    dunningDetails.value = null
    cashAllocations.value = {}

    if (selectedReview.value.review_type === "CASH_APPLICATION_REVIEW") {
      const r = await fetch(`http://127.0.0.1:8000/reviews/${id}/cash-details`)
      if (!r.ok) throw new Error("Could not load cash details")
      cashDetails.value = await r.json()
    } else if (selectedReview.value.review_type === "INVOICE_QA_REVIEW") {
      const r = await fetch(`http://127.0.0.1:8000/reviews/${id}/invoice-qa-details`)
      if (!r.ok) throw new Error("Could not load invoice QA details")
      invoiceQaDetails.value = await r.json()
    } else if (selectedReview.value.review_type === "DUNNING_REVIEW") {
      const r = await fetch(`http://127.0.0.1:8000/reviews/${id}/dunning-details`)
      if (!r.ok) throw new Error("Could not load dunning details")
      dunningDetails.value = await r.json()
    }
  } catch (err) {
    console.error(err)
    alert("Could not load review details.")
  }
}

async function resolveReview(action) {
  const response = await fetch(`http://127.0.0.1:8000/reviews/${selectedReview.value.review_id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  })
  if (!response.ok) {
    const data = await response.json()
    alert(data.detail || "Could not resolve review")
    return
  }
  selectedReview.value = null
  await loadReviews()
  await loadAllReviews()
  await loadAgentActions()
}

async function resolveCashReview(action) {
  const allocations = Object.entries(cashAllocations.value)
    .filter(([, amount]) => Number(amount) > 0)
    .map(([invoice_id, amount]) => ({ invoice_id, amount: Number(amount) }))
  const response = await fetch(`http://127.0.0.1:8000/reviews/${selectedReview.value.review_id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, allocations: action === "MATCH" ? allocations : null })
  })
  if (!response.ok) {
    const data = await response.json()
    alert(data.detail || "Could not resolve cash application review")
    return
  }
  selectedReview.value = null
  cashDetails.value = null
  cashAllocations.value = {}
  await loadReviews()
  await loadAllReviews()
  await loadAgentActions()
}

async function loadAgentActions() {
  try {
    const response = await fetch("http://127.0.0.1:8000/agent-actions")
    if (!response.ok) throw new Error("Could not load agent actions")
    agentActions.value = await response.json()
  } catch (err) {
    console.error(err)
    error.value = "Could not load agent activity."
  }
}

async function searchCase() {
  if (!caseId.value.trim()) return
  try {
    const response = await fetch(`http://127.0.0.1:8000/cases/${caseId.value.trim()}`)
    if (!response.ok) {
      caseOverview.value = null
      alert("Case not found")
      return
    }
    caseOverview.value = await response.json()
  } catch (err) {
    console.error(err)
    alert("Could not load case.")
  }
}

onMounted(async () => {
  await loadAllReviews()
  await loadAgentActions()
})
</script>

<template>
  <div class="dashboard">
    <aside class="sidebar">
      <div class="brand">
        <h2>O2C Agents</h2>
        <span>Operations Console</span>
      </div>
      <nav>
        <button v-for="section in sections" :key="section.value" :class="{ active: selectedSection === section.value }" @click="loadSection(section.value)">
          {{ section.label }}
          <span v-if="reviewSections.includes(section.value)" class="badge">{{ countType(section.value) }}</span>
        </button>
      </nav>
    </aside>

    <main class="content">
      <header class="page-header">
        <div>
          <h1>{{ currentTitle }}</h1>
          <p>Order-to-Cash agent operations and human review</p>
        </div>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="selectedSection === 'OVERVIEW'">
        <div class="stats-grid">
          <div class="stat-card"><span>Open Reviews</span><strong>{{ openCount }}</strong></div>
          <div class="stat-card"><span>Invoice QA</span><strong>{{ countType('INVOICE_QA_REVIEW') }}</strong></div>
          <div class="stat-card"><span>Cash Application</span><strong>{{ countType('CASH_APPLICATION_REVIEW') }}</strong></div>
          <div class="stat-card"><span>Dunning</span><strong>{{ countType('DUNNING_REVIEW') }}</strong></div>
        </div>
        <section class="panel">
          <div class="panel-heading"><div><h2>Recent Agent Activity</h2><p>Latest automated decisions and escalations</p></div></div>
          <div v-for="action in agentActions.slice(0, 8)" :key="action.action_id" class="activity-row">
            <div><strong>{{ action.agent_name }}</strong><span>{{ action.entity_type }} · {{ action.entity_id }}</span></div>
            <div><strong>{{ action.decision }}</strong><span>{{ action.status }} · {{ action.confidence ?? '—' }}</span></div>
            <p>{{ action.reason }}</p>
          </div>
        </section>
      </div>

      <div v-else-if="reviewSections.includes(selectedSection)" class="review-layout">
        <section class="queue panel">
          <div class="panel-heading"><div><h2>Open Reviews</h2><p>{{ reviews.length }} cases awaiting action</p></div></div>
          <p v-if="loading">Loading...</p>
          <p v-else-if="reviews.length === 0">No open reviews.</p>
          <article v-for="review in reviews" :key="review.review_id" class="review-card" :class="{ selected: selectedReview?.review_id === review.review_id }" @click="openReview(review.review_id)">
            <div class="review-card-header"><strong>{{ review.entity_id }}</strong><span>{{ review.status }}</span></div>
            <p>{{ review.reason }}</p>
            <small>{{ new Date(review.created_at).toLocaleString() }}</small>
          </article>
        </section>

        <section class="detail panel">
          <div v-if="selectedReview">
            <div class="detail-title"><div><h2>{{ selectedReview.entity_id }}</h2><p class="status">{{ selectedReview.review_type.replaceAll('_', ' ') }} · {{ selectedReview.status }}</p></div></div>
            <h3>AI Analysis</h3><p>{{ selectedReview.reason }}</p>
            <h3>Recommended Action</h3><p>{{ selectedReview.recommended_action }}</p>

            <div v-if="selectedReview.review_type === 'INVOICE_QA_REVIEW' && invoiceQaDetails">
              <h3>3-Way Match Evidence</h3>
              <div class="info-box">
                <p><strong>Invoice:</strong> {{ invoiceQaDetails.invoice.invoice_id }} — £{{ invoiceQaDetails.invoice.total_amount.toFixed(2) }}</p>
                <p><strong>Purchase Order:</strong> {{ invoiceQaDetails.purchase_order.po_id }} — £{{ invoiceQaDetails.purchase_order.expected_total.toFixed(2) }}</p>
                <p><strong>GRN:</strong> {{ invoiceQaDetails.grn.grn_id }} — {{ invoiceQaDetails.grn.status }}</p>
              </div>
              <h3>Line Items</h3>
              <div v-for="line in invoiceQaDetails.lines" :key="line.line_id" class="line-item">
                <strong>{{ line.description }}</strong>
                <p>Ordered: {{ line.ordered }} | Received: {{ line.received }} | Billed: {{ line.billed }}</p>
              </div>
              <h3>Contextual Evidence</h3>
              <p v-if="invoiceQaDetails.evidence.length === 0" class="muted">No additional evidence.</p>
              <div v-for="evidence in invoiceQaDetails.evidence" :key="evidence.source + evidence.type + evidence.content" class="evidence">
                <strong>{{ evidence.source }}</strong><span>{{ evidence.source_system }} · {{ evidence.type }}</span><p>{{ evidence.content }}</p>
              </div>
              <div class="actions"><button class="primary" @click="resolveReview('APPROVE')">Approve Invoice</button><button @click="resolveReview('REJECT')">Reject Invoice</button></div>
            </div>

            <div v-else-if="selectedReview.review_type === 'CASH_APPLICATION_REVIEW' && cashDetails">
              <h3>Payment Details</h3>
              <div class="info-box">
                <p><strong>Payment:</strong> {{ cashDetails.payment.payment_id }}</p>
                <p><strong>Amount:</strong> £{{ cashDetails.payment.amount.toFixed(2) }}</p>
                <p><strong>Bank Text:</strong> {{ cashDetails.payment.raw_text }}</p>
              </div>
              <h3>Allocate Payment</h3>
              <p class="muted">Enter the amount to apply to one or more candidate invoices.</p>
              <div v-for="invoice in cashDetails.candidates" :key="invoice.invoice_id" class="allocation-row">
                <div class="allocation-info">
                  <strong>{{ invoice.invoice_id }}</strong><span>{{ invoice.customer }}</span>
                  <small>Invoice £{{ invoice.amount.toFixed(2) }} · Remaining £{{ invoice.remaining.toFixed(2) }}</small>
                </div>
                <div class="allocation-input"><span>£</span><input type="number" min="0" :max="invoice.remaining" step="0.01" v-model="cashAllocations[invoice.invoice_id]" placeholder="0.00" /></div>
              </div>
              <div class="allocation-summary">
                <div><span>Payment</span><strong>£{{ cashDetails.payment.amount.toFixed(2) }}</strong></div>
                <div><span>Allocated</span><strong>£{{ allocatedTotal.toFixed(2) }}</strong></div>
                <div><span>Remaining</span><strong :class="{ warning: Math.abs(paymentRemaining) > 0.01 }">£{{ paymentRemaining.toFixed(2) }}</strong></div>
              </div>
              <div class="actions"><button class="primary" :disabled="Math.abs(paymentRemaining) > 0.01" @click="resolveCashReview('MATCH')">Confirm Allocation</button><button @click="resolveCashReview('LEAVE_UNMATCHED')">Leave Unmatched</button></div>
            </div>

            <div v-else-if="selectedReview.review_type === 'DUNNING_REVIEW' && dunningDetails">
              <h3>Collection Details</h3>
              <div class="info-box">
                <p><strong>Invoice:</strong> {{ dunningDetails.invoice.invoice_id }}</p>
                <p><strong>Customer:</strong> {{ dunningDetails.customer.company_name }}</p>
                <p><strong>Outstanding:</strong> £{{ dunningDetails.invoice.amount.toFixed(2) }}</p>
                <p><strong>Days Overdue:</strong> {{ dunningDetails.invoice.days_overdue }}</p>
                <p><strong>Invoice Status:</strong> {{ dunningDetails.invoice.status }}</p>
              </div>
              <h3>Collection History</h3>
              <p v-if="dunningDetails.history.length === 0" class="muted">No previous collection actions.</p>
              <div v-for="item in dunningDetails.history" :key="item.date + item.type" class="history-item">
                <div class="history-heading"><strong>{{ item.type }}</strong><strong class="history-status">{{ item.status }}</strong></div>
                <p>{{ item.message }}</p><small>{{ new Date(item.date).toLocaleString() }}</small>
              </div>
              <h3>Customer & Payment Evidence</h3>
              <p v-if="dunningDetails.evidence.length === 0" class="muted">No additional contextual evidence.</p>
              <div v-for="evidence in dunningDetails.evidence" :key="evidence.type + evidence.content" class="evidence">
                <strong>{{ evidence.type }}</strong><span>{{ evidence.source }} · {{ evidence.source_system }}</span><p>{{ evidence.content }}</p>
              </div>
              <div class="actions"><button class="primary" @click="resolveReview('SEND_REMINDER')">Send Reminder</button><button @click="resolveReview('WAIT')">Wait</button><button @click="resolveReview('ESCALATE')">Escalate</button></div>
            </div>
          </div>
          <div v-else class="empty-detail"><strong>Select a review</strong><span>Evidence, agent reasoning and human actions will appear here.</span></div>
        </section>
      </div>

      <section v-else-if="selectedSection === 'AGENT_ACTIVITY'" class="panel">
        <div class="panel-heading"><div><h2>Agent Actions</h2><p>Audit trail of automated decisions and escalations</p></div></div>
        <div v-for="action in agentActions" :key="action.action_id" class="activity-row">
          <div><strong>{{ action.agent_name }}</strong><span>{{ action.entity_type }} · {{ action.entity_id }}</span></div>
          <div><strong>{{ action.decision }}</strong><span>{{ action.status }} · confidence {{ action.confidence ?? '—' }}</span></div>
          <p>{{ action.reason }}</p>
        </div>
      </section>

      <section v-else-if="selectedSection === 'CASE_OVERVIEW'" class="case-page">
        <div class="panel case-search-panel">
          <h2>Case Search</h2>
          <p class="muted">Search an invoice, payment or purchase order to reconstruct the related O2C case.</p>
          <div class="case-search"><input v-model="caseId" placeholder="INV-2005, PAY-2004, PO-2005..." @keyup.enter="searchCase" /><button class="primary" @click="searchCase">Search Case</button></div>
        </div>

        <template v-if="caseOverview">
          <div class="case-title"><div><span class="eyebrow">CASE OVERVIEW</span><h2>{{ caseOverview.entity_id }}</h2><p>{{ caseOverview.customers.join(', ') || 'Related O2C records' }}</p></div></div>
          <div class="stats-grid case-stats">
            <div class="stat-card"><span>Invoice Value</span><strong>£{{ caseOverview.stats.invoice_value.toLocaleString() }}</strong></div>
            <div class="stat-card"><span>Invoices</span><strong>{{ caseOverview.stats.invoices }}</strong></div>
            <div class="stat-card"><span>Agent Actions</span><strong>{{ caseOverview.stats.agent_actions }}</strong></div>
            <div class="stat-card"><span>Open Reviews</span><strong>{{ caseOverview.stats.open_reviews }}</strong></div>
          </div>
          <div class="case-grid">
            <section class="panel">
              <h2>Case Summary</h2>
              <div class="summary-box"><p>{{ caseOverview.summary }}</p></div>
              <h3>Related Records</h3>
              <div class="related-group"><strong>Invoices</strong><span v-for="id in caseOverview.related.invoices" :key="id" class="entity-chip">{{ id }}</span></div>
              <div class="related-group"><strong>Payments</strong><span v-if="caseOverview.related.payments.length === 0" class="muted">None</span><span v-for="id in caseOverview.related.payments" :key="id" class="entity-chip">{{ id }}</span></div>
              <div class="related-group"><strong>Purchase Orders</strong><span v-for="id in caseOverview.related.purchase_orders" :key="id" class="entity-chip">{{ id }}</span></div>
              <div class="related-group"><strong>GRNs</strong><span v-for="id in caseOverview.related.grns" :key="id" class="entity-chip">{{ id }}</span></div>
              <h3>Invoices</h3>
              <div v-for="invoice in caseOverview.invoices" :key="invoice.invoice_id" class="case-record">
                <div><strong>{{ invoice.invoice_id }}</strong><span>{{ invoice.status }} · QA {{ invoice.qa_status }}</span><small>Due {{ new Date(invoice.due_date).toLocaleDateString() }}</small></div>
                <strong>£{{ invoice.amount.toLocaleString() }}</strong>
              </div>
              <h3>Payments</h3>
              <p v-if="caseOverview.payments.length === 0" class="muted">No linked payment yet.</p>
              <div v-for="payment in caseOverview.payments" :key="payment.payment_id" class="case-record">
                <div><strong>{{ payment.payment_id }}</strong><span>{{ payment.status }}</span><small>{{ payment.bank_text }}</small></div>
                <strong>£{{ payment.amount.toLocaleString() }}</strong>
              </div>
            </section>

            <section class="panel">
              <div class="panel-heading"><div><h2>Case Timeline</h2><p>Evidence, agent decisions, review events and payments</p></div></div>
              <p v-if="caseOverview.timeline.length === 0" class="muted">No timeline events recorded yet.</p>
              <div class="timeline">
                <div v-for="(event, index) in caseOverview.timeline" :key="index" class="timeline-event">
                  <div class="timeline-marker"></div>
                  <div class="timeline-content">
                    <div class="timeline-top"><strong>{{ event.title }}</strong><span class="event-type">{{ event.type }}</span></div>
                    <p>{{ event.detail }}</p>
                    <div class="timeline-meta"><strong>{{ event.status }}</strong><span>{{ new Date(event.date).toLocaleString() }}</span></div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </template>
      </section>
    </main>
  </div>
</template>
