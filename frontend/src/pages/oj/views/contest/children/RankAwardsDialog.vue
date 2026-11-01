<template>
  <LegacyDialog title="晋级 / 奖牌" width="480px" :visible="visible" @update:visible="$emit('update:visible', $event)">
    <RankAwardsEditor v-if="visible" :awards="awards" :official="official" :unit="unit" @change="payload = $event" />
    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('m.Cancel') }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="!payload" @click="save">保存</el-button>
    </template>
  </LegacyDialog>
</template>
<script>
  import api from '@oj/api'
  import RankAwardsEditor from '../RankAwardsEditor.vue'

  export default {
    name: 'RankAwardsDialog',
    components: { RankAwardsEditor },
    props: {
      visible: { type: Boolean, default: false },
      contestId: { type: [String, Number], required: true },
      awards: { type: Object, default: () => ({}) },
      official: { type: Number, default: 0 },
      unit: { type: String, default: '支' }
    },
    emits: ['update:visible', 'saved'],
    data () {
      return { payload: null, saving: false }
    },
    methods: {
      async save () {
        this.saving = true
        try {
          await api.setContestRankAwards(this.contestId, this.payload)
          this.$emit('saved')
          this.$emit('update:visible', false)
        } catch (_) {
          // The API client already shows the error.
        } finally {
          this.saving = false
        }
      }
    }
  }
</script>
