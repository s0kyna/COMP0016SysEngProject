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
const dunningDetails = ref(null)
const cashDetails = ref(null)
const selectedInvoice = ref("")
const invoiceQaDetails = ref(null)

const agentActions = ref([])
const caseId = ref("")
const caseOverview = ref(null)

const reviewSections = [
  "INVOICE_QA_REVIEW",
  "CASH_APPLICATION_REVIEW",
  "DUNNING_REVIEW"
]

const currentTitle = computed(() => {
  return sections.find(x => x.value === selectedSection.value)?.label || ""
})

const openCount = computed(() => allReviews.value.length)

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
  caseOverview.value = null
  error.value = ""
  dunningDetails.value = null

  if (reviewSections.includes(section)) {
    await loadReviews()
  } else if (section === "AGENT_ACTIVITY") {
    await loadAgentActions()
  } else if (section === "OVERVIEW") {
    await loadAllReviews()
    await loadAgentActions()
  }
}

async function loadReviews() {
  loading.value = true

  try {
    const response = await fetch(
      `http://127.0.0.1:8000/reviews?review_type=${selectedSection.value}`
    )

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
    selectedInvoice.value = ""
    invoiceQaDetails.value = null
    dunningDetails.value = null

    if (selectedReview.value.review_type === "CASH_APPLICATION_REVIEW") {
      const cashResponse = await fetch(
        `http://127.0.0.1:8000/reviews/${id}/cash-details`
      )
      if (!cashResponse.ok) throw new Error("Could not load cash details")
      cashDetails.value = await cashResponse.json()
    }

    if (selectedReview.value.review_type === "INVOICE_QA_REVIEW") {
      const qaResponse = await fetch(
        `http://127.0.0.1:8000/reviews/${id}/invoice-qa-details`
      )
      if (!qaResponse.ok) throw new Error("Could not load invoice QA details")
      invoiceQaDetails.value = await qaResponse.json()
    }
    if (selectedReview.value.review_type === "DUNNING_REVIEW") {
      const dunningResponse = await fetch(
        `http://127.0.0.1:8000/reviews/${id}/dunning-details`
      )

      if (!dunningResponse.ok) {
        throw new Error("Could not load dunning details")
      }

      dunningDetails.value = await dunningResponse.json()
    }
  } catch (err) {
    console.error(err)
    alert("Could not load review details.")
  }
}

async function resolveReview(action) {
  const response = await fetch(
    `http://127.0.0.1:8000/reviews/${selectedReview.value.review_id}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action })
    }
  )

  if (!response.ok) {
    const data = await response.json()
    alert(data.detail || "Could not resolve review")
    return
  }

  selectedReview.value = null
  await loadReviews()
  await loadAllReviews()
}

async function resolveCashReview(action) {
  const response = await fetch(
    `http://127.0.0.1:8000/reviews/${selectedReview.value.review_id}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        invoice_id: action === "MATCH" ? selectedInvoice.value : null
      })
    }
  )

  if (!response.ok) {
    const data = await response.json()
    alert(data.detail || "Could not resolve cash application review")
    return
  }

  selectedReview.value = null
  cashDetails.value = null
  selectedInvoice.value = ""
  await loadReviews()
  await loadAllReviews()
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
    const response = await fetch(
      `http://127.0.0.1:8000/cases/${caseId.value.trim()}`
    )

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
        <button
          v-for="section in sections"
          :key="section.value"
          :class="{ active: selectedSection === section.value }"
          @click="loadSection(section.value)"
        >
          {{ section.label }}

          <span
            v-if="reviewSections.includes(section.value)"
            class="badge"
          >
            {{ countType(section.value) }}
          </span>
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

      <!-- OVERVIEW -->
      <div v-if="selectedSection === 'OVERVIEW'">
        <div class="stats-grid">
          <div class="stat-card">
            <span>Open Reviews</span>
            <strong>{{ openCount }}</strong>
          </div>

          <div class="stat-card">
            <span>Invoice QA</span>
            <strong>{{ countType('INVOICE_QA_REVIEW') }}</strong>
          </div>

          <div class="stat-card">
            <span>Cash Application</span>
            <strong>{{ countType('CASH_APPLICATION_REVIEW') }}</strong>
          </div>

          <div class="stat-card">
            <span>Dunning</span>
            <strong>{{ countType('DUNNING_REVIEW') }}</strong>
          </div>
        </div>

        <section class="panel">
          <h2>Recent Agent Activity</h2>

          <div
            v-for="action in agentActions.slice(0, 6)"
            :key="action.action_id"
            class="activity-row"
          >
            <div>
              <strong>{{ action.agent_name }}</strong>
              <span>{{ action.entity_id }}</span>
            </div>

            <div>
              <strong>{{ action.decision }}</strong>
              <span>{{ action.status }}</span>
            </div>
          </div>
        </section>
      </div>

      <!-- REVIEW QUEUES -->
      <div
        v-else-if="reviewSections.includes(selectedSection)"
        class="review-layout"
      >
        <section class="queue panel">
          <div class="panel-heading">
            <div>
              <h2>Open Reviews</h2>
              <p>{{ reviews.length }} cases awaiting action</p>
            </div>
          </div>

          <p v-if="loading">Loading...</p>
          <p v-else-if="reviews.length === 0">No open reviews.</p>

          <article
            v-for="review in reviews"
            :key="review.review_id"
            class="review-card"
            :class="{
              selected:
                selectedReview?.review_id === review.review_id
            }"
            @click="openReview(review.review_id)"
          >
            <div class="review-card-header">
              <strong>{{ review.entity_id }}</strong>
              <span>{{ review.status }}</span>
            </div>

            <p>{{ review.reason }}</p>

            <small>{{ review.created_at }}</small>
          </article>
        </section>

        <section class="detail panel">
          <div v-if="selectedReview">
            <h2>{{ selectedReview.entity_id }}</h2>
            <p class="status">
              {{ selectedReview.review_type }}
              · {{ selectedReview.status }}
            </p>

            <h3>AI Analysis</h3>
            <p>{{ selectedReview.reason }}</p>

            <h3>Recommended Action</h3>
            <p>{{ selectedReview.recommended_action }}</p>

            <!-- INVOICE QA -->
            <div
              v-if="
                selectedReview.review_type === 'INVOICE_QA_REVIEW'
                && invoiceQaDetails
              "
            >
              <h3>3-Way Match Evidence</h3>

              <div class="info-box">
                <p>
                  <strong>Invoice:</strong>
                  {{ invoiceQaDetails.invoice.invoice_id }}
                  — £{{ invoiceQaDetails.invoice.total_amount.toFixed(2) }}
                </p>

                <p>
                  <strong>Purchase Order:</strong>
                  {{ invoiceQaDetails.purchase_order.po_id }}
                  — £{{ invoiceQaDetails.purchase_order.expected_total.toFixed(2) }}
                </p>

                <p>
                  <strong>GRN:</strong>
                  {{ invoiceQaDetails.grn.grn_id }}
                  — {{ invoiceQaDetails.grn.status }}
                </p>
              </div>

              <h3>Line Items</h3>

              <div
                v-for="line in invoiceQaDetails.lines"
                :key="line.line_id"
                class="line-item"
              >
                <strong>{{ line.description }}</strong>
                <p>
                  Ordered: {{ line.ordered }} |
                  Received: {{ line.received }} |
                  Billed: {{ line.billed }}
                </p>
              </div>

              <h3>Contextual Evidence</h3>

              <div
                v-for="evidence in invoiceQaDetails.evidence"
                :key="evidence.source + evidence.type + evidence.content"
                class="evidence"
              >
                <strong>{{ evidence.source }}</strong>
                <span>
                  {{ evidence.source_system }} · {{ evidence.type }}
                </span>
                <p>{{ evidence.content }}</p>
              </div>

              <div class="actions">
                <button @click="resolveReview('APPROVE')">
                  Approve Invoice
                </button>

                <button @click="resolveReview('REJECT')">
                  Reject Invoice
                </button>
              </div>
            </div>

            <!-- CASH -->
            <div
              v-else-if="
                selectedReview.review_type === 'CASH_APPLICATION_REVIEW'
                && cashDetails
              "
            >
              <h3>Payment Details</h3>

              <div class="info-box">
                <p>
                  <strong>Payment:</strong>
                  {{ cashDetails.payment.payment_id }}
                </p>

                <p>
                  <strong>Amount:</strong>
                  £{{ cashDetails.payment.amount.toFixed(2) }}
                </p>

                <p>
                  <strong>Bank Text:</strong>
                  {{ cashDetails.payment.raw_text }}
                </p>
              </div>

              <h3>Candidate Invoices</h3>

              <label
                v-for="invoice in cashDetails.candidates"
                :key="invoice.invoice_id"
                class="candidate"
                :class="{ selected: selectedInvoice === invoice.invoice_id }"
              >
                <input
                  type="radio"
                  :value="invoice.invoice_id"
                  v-model="selectedInvoice"
                />

                <span>
                  <strong>{{ invoice.invoice_id }}</strong>
                  — £{{ invoice.amount.toFixed(2) }}
                  — {{ invoice.status }}
                </span>
              </label>

              <div class="actions">
                <button
                  :disabled="!selectedInvoice"
                  @click="resolveCashReview('MATCH')"
                >
                  Match Selected Invoice
                </button>

                <button @click="resolveCashReview('LEAVE_UNMATCHED')">
                  Leave Unmatched
                </button>
              </div>
            </div>

            <!-- DUNNING -->
            <!-- DUNNING -->
            <div
              v-else-if="
                selectedReview.review_type === 'DUNNING_REVIEW'
                && dunningDetails
              "
            >
              <h3>Collection Details</h3>

              <div class="info-box">
                <p>
                  <strong>Invoice:</strong>
                  {{ dunningDetails.invoice.invoice_id }}
                </p>

                <p>
                  <strong>Customer:</strong>
                  {{ dunningDetails.customer.company_name }}
                </p>

                <p>
                  <strong>Outstanding:</strong>
                  £{{ dunningDetails.invoice.amount.toFixed(2) }}
                </p>

                <p>
                  <strong>Days Overdue:</strong>
                  {{ dunningDetails.invoice.days_overdue }}
                </p>

                <p>
                  <strong>Invoice Status:</strong>
                  {{ dunningDetails.invoice.status }}
                </p>
              </div>

              <h3>Collection History</h3>

              <p v-if="dunningDetails.history.length === 0">
                No previous collection actions.
              </p>

              <div
                v-for="item in dunningDetails.history"
                :key="item.date + item.type"
                class="history-item"
              >
                <strong>{{ item.type }}</strong>
                <span>{{ item.status }}</span>
                <p>{{ item.message }}</p>
              </div>

              <h3>Customer & Payment Evidence</h3>

              <p v-if="dunningDetails.evidence.length === 0">
                No additional contextual evidence.
              </p>

              <div
                v-for="evidence in dunningDetails.evidence"
                :key="evidence.type + evidence.content"
                class="evidence"
              >
                <strong>{{ evidence.type }}</strong>
                <span>
                  {{ evidence.source }} · {{ evidence.source_system }}
                </span>
                <p>{{ evidence.content }}</p>
              </div>

              <div class="actions">
                <button @click="resolveReview('SEND_REMINDER')">
                  Send Reminder
                </button>

                <button @click="resolveReview('WAIT')">
                  Wait
                </button>

                <button @click="resolveReview('ESCALATE')">
                  Escalate
                </button>
              </div>
            </div>
          </div>

          <div v-else class="empty-detail">
            Select a review to inspect the case.
          </div>
        </section>
      </div>

      <!-- AGENT ACTIVITY -->
      <section
        v-else-if="selectedSection === 'AGENT_ACTIVITY'"
        class="panel"
      >
        <h2>Agent Actions</h2>

        <div
          v-for="action in agentActions"
          :key="action.action_id"
          class="activity-row"
        >
          <div>
            <strong>{{ action.agent_name }}</strong>
            <span>
              {{ action.entity_type }} · {{ action.entity_id }}
            </span>
          </div>

          <div>
            <strong>{{ action.decision }}</strong>
            <span>
              {{ action.status }}
              · {{ action.confidence }}
            </span>
          </div>

          <p>{{ action.reason }}</p>
        </div>
      </section>

      <!-- CASE OVERVIEW -->
      <section
        v-else-if="selectedSection === 'CASE_OVERVIEW'"
        class="panel"
      >
        <h2>Case Overview</h2>
        <p>
          Search an invoice or payment ID to see the complete agent history.
        </p>

        <div class="case-search">
          <input
            v-model="caseId"
            placeholder="e.g. INV-9901 or PAY-77881"
            @keyup.enter="searchCase"
          />

          <button @click="searchCase">Search</button>
        </div>

        <div v-if="caseOverview" class="case-overview">
          <h3>{{ caseOverview.entity_id }}</h3>

          <div class="summary-box">
            <strong>Summary</strong>
            <p>{{ caseOverview.summary }}</p>
          </div>

          <h3>Agent History</h3>

          <div
            v-for="action in caseOverview.agent_actions"
            :key="action.action_id"
            class="activity-row"
          >
            <div>
              <strong>{{ action.agent_name }}</strong>
              <span>{{ action.decision }}</span>
            </div>

            <p>{{ action.reason }}</p>
          </div>

          <h3>Human Reviews</h3>

          <div
            v-for="review in caseOverview.reviews"
            :key="review.review_id"
            class="review-card"
          >
            <strong>{{ review.review_type }}</strong>
            <p>{{ review.reason }}</p>
            <span>{{ review.status }}</span>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>