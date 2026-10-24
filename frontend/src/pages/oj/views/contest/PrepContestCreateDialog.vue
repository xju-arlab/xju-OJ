<template>
  <LegacyDialog :title="$t('m.Create_Prep_Contest')"
                width="600px"
                :visible="visible"
                @update:visible="$emit('update:visible', $event)">
    <p class="prep-create-intro">{{ $t('m.Create_Prep_Contest_Intro') }}</p>
    <el-form ref="form" :model="form" :rules="rules" label-position="top" class="prep-create-form">
      <el-form-item prop="title" :label="$t('m.Title')">
        <el-input v-model="form.title" maxlength="128"></el-input>
      </el-form-item>
      <div class="prep-create-grid">
        <el-form-item :label="$t('m.Contest_Rule_Type')">
          <el-select v-model="form.rule_type" class="full-control">
            <el-option label="ACM" value="ACM"></el-option>
            <el-option label="OI" value="OI"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('m.Contest_Password')">
          <el-input v-model="form.password" maxlength="32" :placeholder="$t('m.Prep_Password_Placeholder')"></el-input>
        </el-form-item>
        <el-form-item prop="start_time" :label="$t('m.Contest_Start_Time')">
          <el-date-picker v-model="form.start_time" type="datetime" class="full-control"></el-date-picker>
        </el-form-item>
        <el-form-item prop="end_time" :label="$t('m.Contest_End_Time')">
          <el-date-picker v-model="form.end_time" type="datetime" class="full-control"></el-date-picker>
        </el-form-item>
      </div>
      <el-form-item :label="$t('m.ContestDescription')">
        <el-input v-model="form.description" type="textarea" :rows="3"></el-input>
      </el-form-item>
      <label class="prep-create-switch">
        <span>{{ $t('m.Real_Time_Rank') }}</span>
        <el-switch v-model="form.real_time_rank"></el-switch>
      </label>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('m.Cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="submit">{{ $t('m.Create_Contest') }}</el-button>
    </template>
  </LegacyDialog>
</template>

<script>
import api from '@oj/api'

const HOUR = 3600 * 1000

function defaultForm () {
  // Default to tomorrow 09:00, five hours long; the creator adjusts it when publishing.
  const start = new Date()
  start.setDate(start.getDate() + 1)
  start.setHours(9, 0, 0, 0)
  return {
    title: '',
    rule_type: 'ACM',
    password: '',
    start_time: start,
    end_time: new Date(start.getTime() + 5 * HOUR),
    description: '',
    real_time_rank: true
  }
}

export default {
  name: 'PrepContestCreateDialog',
  props: { visible: { type: Boolean, default: false } },
  emits: ['update:visible', 'created'],
  data () {
    return {
      form: defaultForm(),
      saving: false,
      rules: {
        title: { required: true, message: this.$t('m.Prep_Title_Required'), trigger: 'blur' },
        start_time: { required: true, trigger: 'change' },
        end_time: { required: true, trigger: 'change' }
      }
    }
  },
  watch: {
    visible (value) {
      if (value) this.form = defaultForm()
    }
  },
  methods: {
    async submit () {
      try {
        await this.$refs.form.validate()
      } catch (_) {
        return
      }
      if (new Date(this.form.end_time) <= new Date(this.form.start_time)) {
        this.$error(this.$t('m.Prep_Time_Invalid'))
        return
      }
      this.saving = true
      try {
        const res = await api.createPrepContest({
          title: this.form.title,
          description: this.form.description,
          rule_type: this.form.rule_type,
          password: this.form.password,
          start_time: new Date(this.form.start_time).toISOString(),
          end_time: new Date(this.form.end_time).toISOString(),
          real_time_rank: this.form.real_time_rank,
          visible: true,
          allowed_ip_ranges: []
        })
        this.$emit('update:visible', false)
        this.$emit('created', res.data.data)
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.saving = false
      }
    }
  }
}
</script>

<style scoped lang="less">
.prep-create-intro { margin: 0 0 14px; color: var(--color-text-muted); font-size: 13px; line-height: 1.6; }
.prep-create-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.full-control { width: 100%; }
.prep-create-switch { display: flex; align-items: center; justify-content: space-between; padding: 8px 0 0; color: var(--color-text-muted); font-size: 13px; }
:deep(.el-date-editor.el-input) { width: 100%; }
@media (max-width: 560px) {
  .prep-create-grid { grid-template-columns: 1fr; }
}
</style>
