<script setup>
import { ref, onMounted } from "vue"

const reviewTypes = [
  { label: "Invoice QA", value: "INVOICE_QA_REVIEW" },
  { label: "Cash Application", value: "CASH_APPLICATION_REVIEW" },
  { label: "Dunning", value: "DUNNING_REVIEW" }
]

const selectedType = ref("INVOICE_QA_REVIEW")
const reviews = ref([])
const selectedReview = ref(null)
const loading = ref(false)

async function loadReviews() {
  loading.value = true
  selectedReview.value = null

  const response = await fetch(
    `http://127.0.0.1:8000/reviews?review_type=${selectedType.value}`
  )

  reviews.value = await response.json()
  loading.value = false
}

function selectType(type) {
  selectedType.value = type
  loadReviews()
}

async function openReview(id) {
  const response = await fetch(`http://127.0.0.1:8000/reviews/${id}`)
  selectedReview.value = await response.json()
}

onMounted(loadReviews)
</script>

<template>
  <main>
    <h1>Human Review Dashboard</h1>
    <p class="subtitle">Cases escalated by the O2C agents</p>

    <div class="tabs">
      <button
        v-for="type in reviewTypes"
        :key="type.value"
        :class="{ active: selectedType === type.value }"
        @click="selectType(type.value)"
      >
        {{ type.label }}
      </button>
    </div>

    <p v-if="loading">Loading...</p>

    <div v-else class="layout">
      <section class="queue">
        <h2>Open Reviews</h2>

        <p v-if="reviews.length === 0">No open reviews.</p>

        <article
          v-for="review in reviews"
          :key="review.review_id"
          class="card"
          @click="openReview(review.review_id)"
        >
          <strong>{{ review.entity_id }}</strong>
          <span>{{ review.review_type }}</span>
          <p>{{ review.reason }}</p>
          <button>Review</button>
        </article>
      </section>

      <section class="detail">
        <div v-if="selectedReview">
          <h2>{{ selectedReview.entity_id }}</h2>
          <p><strong>Status:</strong> {{ selectedReview.status }}</p>

          <h3>AI Analysis</h3>
          <p>{{ selectedReview.reason }}</p>

          <h3>Recommended Action</h3>
          <p>{{ selectedReview.recommended_action }}</p>
        </div>

        <p v-else>Select a review to see details.</p>
      </section>
    </div>
  </main>
</template>

<style>
body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: #f5f6f8;
  color: #222;
}

main {
  max-width: 1100px;
  margin: auto;
  padding: 32px;
}

h1 {
  margin-bottom: 4px;
}

.subtitle {
  color: #666;
  margin-top: 0;
}

.tabs {
  display: flex;
  gap: 10px;
  margin: 28px 0;
}

.tabs button {
  padding: 10px 16px;
  border: 1px solid #ccc;
  background: white;
  cursor: pointer;
  border-radius: 6px;
}

.tabs button.active {
  background: #222;
  color: white;
}

.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.queue, .detail {
  background: white;
  padding: 20px;
  border-radius: 8px;
}

.card {
  border: 1px solid #ddd;
  padding: 16px;
  margin-bottom: 12px;
  border-radius: 6px;
  cursor: pointer;
}

.card span {
  display: block;
  font-size: 12px;
  color: #777;
  margin-top: 4px;
}

.card button {
  padding: 7px 12px;
}

@media (max-width: 700px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>