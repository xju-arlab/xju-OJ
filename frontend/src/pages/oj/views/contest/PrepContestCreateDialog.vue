<template>
  <LegacyDialog :title="$t('m.Create_Prep_Contest')"
                width="600px"
                :visible="visible"
                @update:visible="$emit('update:visible', $event)">
    <el-form ref="form" :model="form" :rules="rules" label-position="top" class="prep-create-form">
      <el-form-item prop="title" :label="$t('m.Contest_Name')">
        <el-input v-model="form.title" maxlength="128" :placeholder="$t('m.Contest_Name')"></el-input>
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

// The contest window is chosen when publishing, not while preparing.
function defaultForm () {
  return {
    title: '',
    rule_type: 'ACM',
    password: '',
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
        title: { required: true, message: this.$t('m.Prep_Title_Required'), trigger: 'blur' }
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
      this.saving = true
      try {
        const res = await api.createPrepContest({
          title: this.form.title,
          description: this.form.description,
          rule_type: this.form.rule_type,
          password: this.form.password,
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
.prep-create-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.full-control { width: 100%; }
.prep-create-switch { display: flex; align-items: center; justify-content: space-between; padding: 8px 0 0; color: var(--color-text-muted); font-size: 13px; }
@media (max-width: 560px) {
  .prep-create-grid { grid-template-columns: 1fr; }
}
</style>
