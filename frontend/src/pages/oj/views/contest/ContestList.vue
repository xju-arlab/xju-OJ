<template>
  <Row type="flex">
    <Col :span="24">
    <Panel id="contest-card" shadow>
      <template #title><div >{{query.rule_type === '' ? this.$t('m.All') : query.rule_type}} {{$t('m.Contests')}}</div></template>
      <template #extra><div class="contest-filters">
        <Dropdown @on-click="onRuleChange">
          <button type="button" class="contest-filter-control">
            <span>{{query.rule_type === '' ? this.$t('m.Rule') : this.$t('m.' + query.rule_type)}}</span>
            <Icon type="arrow-down-b"></Icon>
          </button>
          <template #list><Dropdown-menu>
            <Dropdown-item name="">{{$t('m.All')}}</Dropdown-item>
            <Dropdown-item name="OI">{{$t('m.OI')}}</Dropdown-item>
            <Dropdown-item name="ACM">{{$t('m.ACM')}}</Dropdown-item>
          </Dropdown-menu></template>
        </Dropdown>
        <Dropdown @on-click="onStatusChange">
          <button type="button" class="contest-filter-control">
            <span>{{statusFilterLabel}}</span>
            <Icon type="arrow-down-b"></Icon>
          </button>
          <template #list><Dropdown-menu>
            <Dropdown-item name="">{{$t('m.All')}}</Dropdown-item>
            <Dropdown-item name="0">{{$t('m.Underway')}}</Dropdown-item>
            <Dropdown-item name="1">{{$t('m.Not_Started')}}</Dropdown-item>
            <Dropdown-item name="-1">{{$t('m.Ended')}}</Dropdown-item>
          </Dropdown-menu></template>
        </Dropdown>
          <Input id="keyword" class="contest-keyword" @on-enter="changeRoute" @on-click="changeRoute" v-model="query.keyword"
               icon="ios-search-strong" :placeholder="$t('m.Search_Contests')"/>
      </div></template>
      <p id="no-contest" v-if="contests.length == 0">{{$t('m.No_contest')}}</p>
      <ol id="contest-list">
        <li v-for="contest in contests" :key="contest.title">
          <div class="contest-row">
            <span class="contest-logo" aria-hidden="true"><Icon type="trophy" /></span>
            <div class="contest-main">
              <p class="title">
                <a class="entry" @click.stop="goContest(contest)">{{contest.title}}</a>
                <Icon v-if="contest.contest_type != 'Public' && !isEnded(contest)" type="ios-locked-outline" size="16"></Icon>
              </p>
              <ul class="detail">
                <li><Icon type="calendar" />{{ $filters.localtime(contest.start_time, 'YYYY-M-D HH:mm') }}</li>
                <li><Icon type="android-time" />{{getDuration(contest.start_time, contest.end_time)}}</li>
                <li><span :class="['contest-rule', ruleClass(contest.rule_type)]">{{contest.rule_type}}</span></li>
              </ul>
            </div>
            <span :class="['contest-status', statusClass(contest.status)]">{{statusLabel(contest.status)}}</span>
          </div>
        </li>
      </ol>
    </Panel>
    <Pagination :total="total" :page-size="limit" @update:page-size="limit = $event" @on-change="changeRoute" :current="page" @update:current="page = $event" :show-sizer="true" @on-page-size-change="changeRoute"></Pagination>
    </Col>
  </Row>

</template>
<script>
  import api from '@oj/api'
  import utils from '@/utils/utils'
  import Pagination from '@/pages/oj/components/Pagination'
  import { CONTEST_STATUS_REVERSE } from '@/utils/constants'
  import { applyDevelopmentContestFixtures, cloneFixtures, filterMockContests, MOCK_CONTESTS } from '@oj/mocks/fixtures'

  const limit = 10

  export default {
    name: 'contest-list',
    components: {
      Pagination
    },
    data () {
      return {
        page: 1,
        query: {
          status: '',
          keyword: '',
          rule_type: ''
        },
        limit: limit,
        total: 0,
        rows: '',
        contests: [],
        CONTEST_STATUS_REVERSE: CONTEST_STATUS_REVERSE,
//      for password modal use
        cur_contest_id: ''
      }
    },
    mounted () {
      this.init()
    },
    methods: {
      init () {
        let route = this.$route.query
        this.query.status = route.status || ''
        this.query.rule_type = route.rule_type || ''
        this.query.keyword = route.keyword || ''
        this.page = parseInt(route.page) || 1
        this.limit = parseInt(route.limit) || 10
        this.getContestList(this.page)
      },
      getContestList (page = 1) {
        let offset = (page - 1) * this.limit
        api.getContestList(offset, this.limit, this.query).then((res) => {
          const payload = res.data.data || {}
          const results = payload.results || []
          const normalized = applyDevelopmentContestFixtures(results)
          const fallback = filterMockContests(this.query)
          this.contests = normalized.length ? this.withContestProblems(normalized) : cloneFixtures(fallback)
          this.total = payload.total || (normalized.length || fallback.length)
        }, () => {
          const fallback = filterMockContests(this.query)
          this.contests = cloneFixtures(fallback)
          this.total = fallback.length
        })
      },
      changeRoute () {
        let query = Object.assign({}, this.query)
        query.page = this.page
        query.limit = this.limit

        this.$router.push({
          name: 'contest-list',
          query: utils.filterEmptyValue(query)
        })
      },
      onRuleChange (rule) {
        this.query.rule_type = rule
        this.page = 1
        this.changeRoute()
      },
      onStatusChange (status) {
        this.query.status = status
        this.page = 1
        this.changeRoute()
      },
      goContest (contest) {
        this.cur_contest_id = contest.id
        this.$router.push({name: 'contest-problem-list', params: {contestID: contest.id}})
      },

      getDuration (startTime, endTime) {
        const hours = Math.abs(new Date(endTime) - new Date(startTime)) / 3600000
        if (hours >= 24) return this.$t('m.Duration_Days', { count: Math.round(hours / 24) })
        return this.$t('m.Duration_Hours', { count: Number(hours.toFixed(1)) })
      },
      statusLabel (status) {
        const item = CONTEST_STATUS_REVERSE[String(status)]
        return item ? this.$t('m.' + item.name.replace(/ /g, '_')) : this.$t('m.Status')
      },
      statusClass (status) {
        const value = String(status)
        if (value === '1') return 'status-not-started'
        if (value === '-1') return 'status-ended'
        return 'status-underway'
      },
      isEnded (contest) {
        return String(contest.status) === '-1'
      },
      ruleClass (rule) {
        return String(rule).toUpperCase() === 'OI' ? 'rule-oi' : 'rule-acm'
      },
      getProblemLabels (contest) {
        return (contest.problem_ids || contest.problems || []).map(problem => {
          if (typeof problem === 'string' || typeof problem === 'number') return String(problem)
          return problem._id || problem.id || problem.title || ''
        }).filter(Boolean)
      },
      withContestProblems (contests) {
        return contests.map(contest => {
          const fixture = MOCK_CONTESTS.find(item => String(item.id) === String(contest.id))
          return fixture ? { ...contest, problem_ids: fixture.problem_ids } : contest
        })
      }
    },
    computed: {
      statusFilterLabel () {
        if (!this.query.status) return this.$t('m.Status')
        const item = CONTEST_STATUS_REVERSE[String(this.query.status)]
        return item ? this.$t('m.' + item.name.replace(/ /g, '_')) : this.$t('m.Status')
      }
    },
    watch: {
      '$route' (newVal, oldVal) {
        if (newVal !== oldVal) {
          this.init()
        }
      }
    }

  }
</script>
<style lang="less" scoped>
  #contest-card {
    .contest-filters {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      min-height: 34px;
      white-space: nowrap;
    }
    .contest-filter-control {
      display: inline-flex;
      align-items: center;
      justify-content: space-between;
      min-width: 106px;
      height: 34px;
      padding: 0 10px;
      gap: 8px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-sm);
      background: var(--color-bg);
      color: var(--color-text-muted);
      font-size: 13px;
      cursor: pointer;
      transition: background-color var(--transition), border-color var(--transition), color var(--transition);
      &:hover, &:focus-visible {
        border-color: var(--line-strong);
        background: var(--bg-hover);
        color: var(--color-text);
      }
      :deep(.legacy-icon) { display: inline-flex; color: var(--color-text-faint); }
    }
    :deep(.contest-keyword) {
      width: 220px;
      .el-input__wrapper { min-height: 34px; border-radius: var(--radius-sm); }
    }
    #no-contest {
      text-align: center;
      font-size: 16px;
      padding: 20px;
    }
    #contest-list {
      > li {
        padding: 18px 20px;
        border-bottom: 1px solid rgba(187, 187, 187, 0.5);
        list-style: none;
        &:last-child { border-bottom: 0; }
        .contest-row { display: flex; align-items: center; gap: 14px; min-width: 0; }
        .contest-logo {
          display: inline-flex;
          flex: 0 0 38px;
          width: 38px;
          height: 38px;
          align-items: center;
          justify-content: center;
          border: 1px solid var(--color-border);
          border-radius: var(--radius-md);
          background: var(--color-bg-subtle);
          color: var(--cat-course);
          :deep(.legacy-icon) { display: inline-flex; }
        }
        .contest-main {
          min-width: 0;
          flex: 1;
          .title {
            display: flex;
            align-items: center;
            min-width: 0;
            margin: 0;
            font-size: 18px;
            font-weight: 700;
            line-height: 1.35;
            a.entry {
              overflow: hidden;
              color: var(--color-text);
              text-overflow: ellipsis;
              white-space: nowrap;
              &:hover {
                color: var(--color-link);
              }
            }
            :deep(.legacy-icon) { display: inline-flex; flex: none; margin-left: 6px; color: var(--color-text-faint); }
          }
          .detail { display: flex; align-items: center; justify-content: flex-start; flex-wrap: wrap; margin: 7px 0 0; padding: 0; gap: 12px 18px; color: var(--color-text-muted); font-size: 13px; }
          li {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            list-style: none;
            white-space: nowrap;
            :deep(.legacy-icon) { display: inline-flex; color: var(--color-text-faint); }
          }
        }
        .contest-rule { font-weight: 700; letter-spacing: .02em; }
        .rule-oi { color: var(--cat-recommend); }
        .rule-acm { color: var(--cat-course); }
        .contest-status {
          display: inline-flex;
          flex: none;
          min-width: 88px;
          height: 26px;
          align-items: center;
          justify-content: center;
          padding: 0 10px;
          border-radius: var(--radius-sm);
          font-size: 12px;
          font-weight: 600;
          white-space: nowrap;
        }
        .status-not-started { background: var(--tag-tools-bg); color: var(--cat-tools); text-decoration: none; }
        .status-ended { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); text-decoration: none; }
        .status-underway { background: var(--color-bg-subtle); color: var(--color-text-muted); text-decoration: none; }
      }
    }
  }
  @media (max-width: 900px) {
    #contest-card {
      :deep(.el-card__header) { align-items: flex-start; flex-direction: column; gap: 10px; }
      .contest-filters { justify-content: flex-start; flex-wrap: wrap; width: 100%; }
    }
  }
  @media (max-width: 560px) {
    #contest-card {
      .contest-filters { gap: 8px; }
      :deep(.contest-keyword) { flex: 1 1 100%; width: auto; }
      #contest-list > li { padding: 15px 12px; }
      #contest-list > li .contest-row { align-items: flex-start; gap: 10px; }
      #contest-list > li .contest-status { min-width: 78px; }
    }
  }
</style>
