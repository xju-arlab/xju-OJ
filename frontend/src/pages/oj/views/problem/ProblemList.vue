<template>
  <Row type="flex" :gutter="18" class="problem-list-layout">
    <Col :span=19 class="problem-list-main">
    <Panel shadow class="problem-list-panel">
      <template #title><div >{{$t('m.Problem_List')}}</div></template>
      <template #extra><div >
        <div class="problem-filters">
          <Dropdown @on-click="filterByDifficulty">
              <button type="button" class="filter-control difficulty-filter">
                <span>{{query.difficulty === '' ? this.$t('m.Difficulty') : difficultyLabel(query.difficulty)}}</span>
                <Icon type="arrow-down-b"></Icon>
              </button>
              <template #list><Dropdown-menu >
                <Dropdown-item name="">{{$t('m.All')}}</Dropdown-item>
                <Dropdown-item name="Low">{{$t('m.Difficulty_Low')}}</Dropdown-item>
                <Dropdown-item name="Mid" >{{$t('m.Difficulty_Mid')}}</Dropdown-item>
                <Dropdown-item name="High">{{$t('m.Difficulty_High')}}</Dropdown-item>
              </Dropdown-menu></template>
          </Dropdown>
          <button type="button" class="filter-control tags-toggle" :class="{'is-active': tagsVisible}"
                  :aria-pressed="tagsVisible" @click="handleTagsVisible(!tagsVisible)">
            <Icon type="tag"></Icon>
            <span>{{$t('m.Tags')}}</span>
          </button>
          <Input v-model="query.keyword"
                 class="keyword-filter"
                 @on-enter="filterByKeyword"
                 @on-click="filterByKeyword"
                 :placeholder="$t('m.Search_Problems')"
                 icon="ios-search-strong"/>
          <button type="button" class="filter-control reset-filter" @click="onReset">
            <Icon type="refresh"></Icon>
            <span>{{$t('m.Reset')}}</span>
          </button>
        </div>
      </div></template>
      <Table style="width: 100%; font-size: 16px;"
             :columns="problemTableColumns"
             :data="problemList"
             :loading="loadings.table"
             disabled-hover></Table>
    </Panel>
    <Pagination
      :total="total" :page-size="query.limit" @update:page-size="query.limit = $event" @on-change="pushRouter" @on-page-size-change="pushRouter" :current="query.page" @update:current="query.page = $event" :show-sizer="true"></Pagination>

    </Col>

    <Col :span="5" class="problem-tag-sidebar">
    <Panel :padding="10" class="tag-panel">
      <template #title><div  class="taglist-title">{{$t('m.Tags')}}</div></template>
      <div class="tag-grid">
        <button v-for="tag in tagList"
                :key="tag.name"
                type="button"
                @click="filterByTag(tag.name)"
                :class="['tag-btn', {'is-selected': query.tag === tag.name}]"
                :aria-pressed="query.tag === tag.name">{{tag.name}}
        </button>
      </div>

      <LegacyButton long id="pick-one" @click="pickone" class="pick-one-button">
        <Icon type="shuffle"></Icon>
        <span>{{$t('m.Pick_One')}}</span>
      </LegacyButton>
    </Panel>
    <Spin v-if="loadings.tag" fix size="large"></Spin>
    </Col>
  </Row>
</template>
<script>
  import { mapGetters } from '@/store/compat'
  import api from '@oj/api'
  import utils from '@/utils/utils'
  import { ProblemMixin } from '@oj/components/mixins'
  import Pagination from '@oj/components/Pagination'
  import {
    applyDevelopmentProblemFixtures,
    applyDevelopmentTagFixtures,
    cloneFixtures,
    filterMockProblems
  } from '@oj/mocks/fixtures'

  export default {
    name: 'ProblemList',
    mixins: [ProblemMixin],
    components: {
      Pagination
    },
    data () {
      return {
        tagList: [],
        problemTableColumns: [
          {
            title: '#',
            key: '_id',
            width: 80,
            render: (h, params) => {
              return h('Button', {
                props: {
                  type: 'text',
                  size: 'large'
                },
                on: {
                  click: () => {
                    this.$router.push({name: 'problem-details', params: {problemID: params.row._id}})
                  }
                },
                style: {
                  padding: '2px 0'
                }
              }, params.row._id)
            }
          },
          {
            title: this.$t('m.Title'),
            align: 'left',
            width: 400,
            render: (h, params) => {
              return h('button', {
                attrs: { type: 'button' },
                class: 'problem-title-link',
                on: {
                  click: () => {
                    this.$router.push({name: 'problem-details', params: {problemID: params.row._id}})
                  }
                }
              }, params.row.title)
            }
          },
          {
            title: this.$t('m.Level'),
            render: (h, params) => {
              const difficulty = params.row.difficulty || ''
              return h('span', {
                class: ['difficulty-badge', `difficulty-${difficulty.toLowerCase()}`]
              }, difficulty ? this.difficultyLabel(difficulty) : '—')
            }
          },
          {
            title: this.$t('m.Total'),
            key: 'submission_number'
          },
          {
            title: this.$t('m.AC_Rate'),
            render: (h, params) => {
              return h('span', this.getACRate(params.row.accepted_number, params.row.submission_number))
            }
          }
        ],
        problemList: [],
        limit: 20,
        total: 0,
        loadings: {
          table: true,
          tag: true
        },
        routeName: '',
        query: {
          keyword: '',
          difficulty: '',
          tag: '',
          page: 1,
          limit: 20
        },
        tagsVisible: false
      }
    },
    mounted () {
      this.init()
    },
    methods: {
      difficultyLabel (difficulty) {
        return this.$t('m.Difficulty_' + difficulty)
      },
      init (simulate = false) {
        this.routeName = this.$route.name
        let query = this.$route.query
        this.query.difficulty = query.difficulty || ''
        this.query.keyword = query.keyword || ''
        this.query.tag = query.tag || ''
        this.query.page = parseInt(query.page) || 1
        if (this.query.page < 1) {
          this.query.page = 1
        }
        this.query.limit = parseInt(query.limit) || 20
        if (!simulate) {
          this.getTagList()
        }
        this.getProblemList()
      },
      pushRouter () {
        this.$router.push({
          name: 'problem-list',
          query: utils.filterEmptyValue(this.query)
        })
      },
      getProblemList () {
        let offset = (this.query.page - 1) * this.query.limit
        this.loadings.table = true
        api.getProblemList(offset, this.query.limit, this.query).then(res => {
          this.loadings.table = false
          const payload = res.data.data || {}
          const results = payload.results || []
          const normalized = applyDevelopmentProblemFixtures(results)
          const fallback = filterMockProblems(this.query)
          const removedCount = Math.max(0, results.length - normalized.length)
          this.total = payload.total ? Math.max(0, payload.total - removedCount) : (normalized.length || fallback.length)
          this.problemList = normalized.length ? normalized : cloneFixtures(fallback)
          if (this.isAuthenticated) {
            this.addStatusColumn(this.problemTableColumns, this.problemList)
          }
        }, res => {
          this.loadings.table = false
          const fallback = filterMockProblems(this.query)
          this.total = fallback.length
          this.problemList = cloneFixtures(fallback)
        })
      },
      getTagList () {
        api.getProblemTagList().then(res => {
          const normalized = applyDevelopmentTagFixtures(res.data.data || [])
          this.tagList = normalized.length ? normalized : this.getMockTags()
          this.loadings.tag = false
        }, res => {
          this.tagList = this.getMockTags()
          this.loadings.tag = false
        })
      },
      getMockTags () {
        if (!import.meta.env.DEV) return []
        return [
          { name: 'math' },
          { name: 'beginner' },
          { name: 'precision' }
        ]
      },
      filterByTag (tagName) {
        this.query.tag = this.query.tag === tagName ? '' : tagName
        this.query.page = 1
        this.pushRouter()
      },
      filterByDifficulty (difficulty) {
        this.query.difficulty = difficulty
        this.query.page = 1
        this.pushRouter()
      },
      filterByKeyword () {
        this.query.page = 1
        this.pushRouter()
      },
      handleTagsVisible (value) {
        if (Boolean(value) === this.tagsVisible) return
        this.tagsVisible = Boolean(value)
        const tagsColumnIndex = this.problemTableColumns.findIndex(column => column.key === 'tags')
        if (this.tagsVisible && tagsColumnIndex === -1) {
          this.problemTableColumns = this.problemTableColumns.concat({
              key: 'tags',
              title: this.$t('m.Tags'),
              align: 'center',
              render: (h, params) => {
                const tags = (params.row.tags || []).map(tag => {
                  const label = typeof tag === 'string' ? tag : tag.name
                  return h('span', { class: 'table-tag-chip' }, label)
                })
                return h('div', {
                  class: 'table-tag-list'
                }, tags)
              }
            })
        } else if (!this.tagsVisible && tagsColumnIndex !== -1) {
          this.problemTableColumns = this.problemTableColumns.filter((column, index) => index !== tagsColumnIndex)
        }
      },
      onReset () {
        this.$router.push({name: 'problem-list'})
      },
      pickone () {
        api.pickone().then(res => {
          this.$success('Good Luck')
          this.$router.push({name: 'problem-details', params: {problemID: res.data.data}})
        })
      }
    },
    computed: {
      ...mapGetters(['isAuthenticated'])
    },
    watch: {
      '$route' (newVal, oldVal) {
        if (newVal !== oldVal) {
          this.init(true)
        }
      },
      'isAuthenticated' (newVal) {
        if (newVal === true) {
          this.init()
        }
      }
    }
  }
</script>

<style scoped lang="less">
  .problem-list-panel :deep(.el-card__header) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }

  .problem-list-panel :deep(.panel-title) { flex: none; }
  .problem-list-panel :deep(.panel-extra) { min-width: 0; flex: 1; line-height: normal; }

  .problem-filters {
    display: flex;
    min-width: 0;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    white-space: nowrap;
  }

  .filter-control {
    appearance: none;
    display: inline-flex;
    height: 34px;
    align-items: center;
    justify-content: center;
    gap: 7px;
    padding: 0 11px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text-muted);
    cursor: pointer;
    transition: color var(--transition), border-color var(--transition), background-color var(--transition);
  }

  .filter-control:hover { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
  .filter-control.is-active { border-color: color-mix(in srgb, var(--cat-kaggle) 28%, var(--color-border)); background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
  .difficulty-filter { min-width: 104px; justify-content: space-between; }
  .keyword-filter { width: 230px; }
  .reset-filter { color: var(--color-text); background: var(--color-bg-subtle); }
  .reset-filter:hover { background: var(--bg-hover); }

  .taglist-title {
    margin: 0;
  }

  .tag-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .tag-btn {
    appearance: none;
    min-width: max-content;
    min-height: 30px;
    overflow: hidden;
    padding: 4px 9px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text-muted);
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
    transition: color var(--transition), border-color var(--transition), background-color var(--transition);
  }
  .tag-btn:hover { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
  .tag-btn.is-selected { border-color: color-mix(in srgb, var(--cat-tools) 30%, var(--color-border)); background: var(--tag-tools-bg); color: var(--cat-tools); font-weight: 600; }

  #pick-one {
    margin-top: 12px;
  }
  .pick-one-button :deep(> span) { display: inline-flex; align-items: center; justify-content: center; gap: 8px; }

  :deep(.difficulty-badge) { display: inline-flex; width: 58px; height: 24px; align-items: center; justify-content: center; border: 1px solid transparent; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; line-height: 1; }
  :deep(.problem-title-link) { appearance: none; display: block; width: 100%; overflow: hidden; padding: 2px 0; border: 0; background: transparent; color: var(--color-text); font: inherit; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
  :deep(.problem-title-link:hover) { color: var(--color-link); }
  :deep(.difficulty-low) { border-color: color-mix(in srgb, var(--cat-tools) 20%, transparent); background: var(--tag-tools-bg); color: var(--cat-tools); }
  :deep(.difficulty-mid) { border-color: color-mix(in srgb, var(--cat-kaggle) 20%, transparent); background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
  :deep(.difficulty-high) { border-color: color-mix(in srgb, var(--cat-research) 20%, transparent); background: var(--tag-research-bg); color: var(--cat-research); }
  :deep(.table-tag-list) { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin: 8px 0; }
  :deep(.table-tag-chip) { display: inline-flex; min-height: 24px; align-items: center; padding: 3px 8px; border-radius: var(--radius-sm); background: var(--color-bg-subtle); color: var(--color-text-muted); font-size: 13px; }

  @media (max-width: 1100px) {
    .problem-list-panel :deep(.el-card__header) { align-items: flex-start; flex-direction: column; }
    .problem-list-panel :deep(.panel-extra) { width: 100%; }
    .problem-filters { justify-content: flex-start; flex-wrap: wrap; }
  }

  @media (max-width: 900px) {
    .problem-list-main, .problem-tag-sidebar { width: 100%; max-width: 100%; flex: 0 0 100%; }
    .problem-tag-sidebar { margin-top: 18px; }
  }

  @media (max-width: 560px) {
    .keyword-filter { order: 5; width: 100%; }
  }
</style>
