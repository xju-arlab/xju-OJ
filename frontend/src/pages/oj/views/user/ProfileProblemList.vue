<template>
  <div class="profile-problem-list">
    <table v-if="problems.length" class="profile-problem-table">
      <thead>
        <tr>
          <th class="id-column">#</th>
          <th>{{ $t('m.Title') }}</th>
          <th class="difficulty-column">{{ $t('m.Level') }}</th>
          <th class="rate-column">{{ $t('m.AC_Rate') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="problem in problems" :key="problem.id">
          <td class="id-column">{{ problem._id }}</td>
          <td class="title-column">
            <router-link :to="{ name: 'problem-details', params: { problemID: problem._id } }">{{ problem.title }}</router-link>
          </td>
          <td class="difficulty-column">{{ problem.difficulty ? $t(`m.Difficulty_${problem.difficulty}`) : '-' }}</td>
          <td class="rate-column">{{ acRate(problem) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="!loading" class="profile-problem-empty">{{ emptyText }}</p>
    <Pagination v-if="total > limit" :total="total" :page-size="limit" :current="page"
                @update:current="page = $event" @on-change="load"></Pagination>
  </div>
</template>

<script>
import api from '@oj/api'
import Pagination from '@oj/components/Pagination.vue'

export default {
  name: 'ProfileProblemList',
  components: { Pagination },
  props: {
    username: { type: String, default: '' },
    // solved | uploaded | favorites
    type: { type: String, required: true },
    emptyText: { type: String, default: '' }
  },
  data () {
    return {
      loading: false,
      problems: [],
      total: 0,
      page: 1,
      limit: 20,
      generation: 0
    }
  },
  mounted () {
    this.load()
  },
  watch: {
    username () {
      this.page = 1
      this.load()
    }
  },
  methods: {
    async load () {
      const generation = ++this.generation
      this.loading = true
      try {
        const res = await api.getProfileProblems({
          type: this.type,
          username: this.username || undefined,
          offset: (this.page - 1) * this.limit,
          limit: this.limit
        })
        if (generation !== this.generation) return
        this.problems = res.data.data.results
        this.total = res.data.data.total
      } catch (_) {
        if (generation === this.generation) this.problems = []
      } finally {
        if (generation === this.generation) this.loading = false
      }
    },
    acRate (problem) {
      if (!problem.submission_number) return '0%'
      return `${Math.round(problem.accepted_number / problem.submission_number * 100)}%`
    }
  }
}
</script>

<style scoped lang="less">
.profile-problem-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  text-align: left;
  th, td { padding: 9px 12px; border-bottom: 1px solid var(--color-border); }
  th { color: var(--color-text-muted); font-size: 13px; font-weight: 600; }
  .title-column a { color: var(--color-text); }
  .title-column a:hover { color: var(--color-link); }
}
.id-column { width: 90px; }
.difficulty-column { width: 90px; }
.rate-column { width: 90px; }
.profile-problem-empty { padding: 26px 0; color: var(--color-text-faint); font-size: 14px; text-align: center; }
@media (max-width: 560px) {
  .difficulty-column, .rate-column { display: none; }
}
</style>
