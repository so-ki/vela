<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { fetchDisclaimer, fetchSsoConfig, register } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Disclaimer } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const disclaimer = ref<Disclaimer | null>(null)
const form = ref({
  email: '',
  password: '',
  full_name: '',
  organization: '',
  role: 'legal' as 'legal' | 'business',
  accept_disclaimer: false,
})
const loading = ref(false)
const error = ref<string | null>(null)
const registrationClosed = ref(false)

onMounted(async () => {
  const [disc, sso] = await Promise.all([fetchDisclaimer(), fetchSsoConfig()])
  disclaimer.value = disc
  if (!sso.allow_open_registration) {
    registrationClosed.value = true
  }
})

async function handleSubmit() {
  if (!form.value.accept_disclaimer) {
    error.value = '注册须勾选同意免责声明与数据使用条款'
    return
  }
  loading.value = true
  error.value = null
  try {
    await register({
      email: form.value.email,
      password: form.value.password,
      full_name: form.value.full_name,
      organization: form.value.organization || undefined,
      role: form.value.role,
      accept_disclaimer: true,
    })
    await auth.login(form.value.email, form.value.password)
    router.push('/')
  } catch (e: unknown) {
    error.value = auth.error || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card wide">
      <div class="auth-header">
        <h1>注册账户</h1>
        <p>选择账户类型并完成注册；请先阅读下方条款并<strong>手动勾选</strong>同意后方可注册</p>
      </div>

      <div v-if="registrationClosed" class="disclaimer-preview">
        <p>当前环境已关闭开放注册。请使用企业 SSO 登录，或联系管理员开通账户。</p>
        <p class="auth-footer">
          <RouterLink to="/login">返回登录</RouterLink>
        </p>
      </div>

      <form v-else @submit.prevent="handleSubmit" class="auth-form">
        <fieldset class="role-choice">
          <legend>账户类型</legend>
          <label class="role-choice-option">
            <input v-model="form.role" type="radio" value="legal" />
            <span class="role-choice-body">
              <strong>法务账户</strong>
              <span class="muted">确认协查范围、Gate A、清单复核、定稿与导出</span>
            </span>
          </label>
          <label class="role-choice-option">
            <input v-model="form.role" type="radio" value="business" />
            <span class="role-choice-body">
              <strong>业务账户</strong>
              <span class="muted">提交投资方案、核对抽取结果、补充材料</span>
            </span>
          </label>
        </fieldset>
        <div class="form-row">
          <label>
            <span>姓名</span>
            <input v-model="form.full_name" required />
          </label>
          <label>
            <span>所属企业</span>
            <input v-model="form.organization" />
          </label>
        </div>
        <label>
          <span>工作邮箱</span>
          <input v-model="form.email" type="email" required />
        </label>
        <label>
          <span>密码（至少 8 位）</span>
          <input v-model="form.password" type="password" minlength="8" required />
        </label>

        <div class="disclaimer-preview" v-if="disclaimer">
          <h3>{{ disclaimer.title }}</h3>
          <div class="preview-scroll">
            <section v-for="s in disclaimer.sections" :key="s.title">
              <strong>{{ s.title }}</strong>
              <p>{{ s.content }}</p>
            </section>
          </div>
        </div>

        <label class="checkbox-row">
          <input type="checkbox" v-model="form.accept_disclaimer" required />
          <span>我已阅读并同意免责声明与数据使用条款</span>
        </label>

        <p class="error" v-if="error">{{ error }}</p>

        <button type="submit" class="btn-primary full" :disabled="loading || !form.accept_disclaimer">
          {{ loading ? '注册中…' : '注册并登录' }}
        </button>
      </form>

      <p class="auth-footer" v-if="!registrationClosed">
        已有账户？<RouterLink to="/login">返回登录</RouterLink>
      </p>
    </div>
  </div>
</template>
