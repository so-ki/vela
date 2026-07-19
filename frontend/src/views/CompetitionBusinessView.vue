<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  confirmCompetitionBusinessFact,
  fetchCompetitionBusinessCenter,
  submitCompetitionBusinessSupplement,
  uploadCompetitionBusinessMaterial,
} from '@/api/client'
import type { CompetitionBusinessCenter } from '@/types/competition'

const route = useRoute()
const scenarioId = computed(() => Number(route.params.id))
const center = ref<CompetitionBusinessCenter | null>(null)
const factDrafts = ref<Record<string, string>>({})
const projectFileInput = ref<HTMLInputElement | null>(null)
const supplementFileInput = ref<HTMLInputElement | null>(null)
const loading = ref(true)
const busy = ref(false)
const notice = ref('')
const error = ref('')

function applyCenter(next: CompetitionBusinessCenter) {
  center.value = next
  factDrafts.value = Object.fromEntries(next.facts.map((fact) => [fact.id, fact.value]))
}

async function loadCenter() {
  loading.value = true
  error.value = ''
  try {
    applyCenter(await fetchCompetitionBusinessCenter(scenarioId.value))
  } catch {
    error.value = '业务中心暂时无法加载，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function uploadMaterial(purpose: 'project' | 'supplement', event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    applyCenter(await uploadCompetitionBusinessMaterial(scenarioId.value, purpose, file))
    notice.value = purpose === 'supplement' ? '补充材料已上传，请提交法务。' : '项目材料已上传。'
  } catch {
    error.value = '材料上传失败，请检查文件后重试。'
  } finally {
    busy.value = false
    input.value = ''
  }
}

async function confirmFacts() {
  if (!center.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    let next = center.value
    for (const fact of center.value.facts) {
      next = await confirmCompetitionBusinessFact(
        scenarioId.value,
        fact.id,
        factDrafts.value[fact.id] || fact.value,
      )
    }
    applyCenter(next)
    notice.value = '事实已确认；如有更正，法务将按最新信息复核。'
  } catch {
    error.value = '事实确认失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}

async function submitToLegal() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    applyCenter(await submitCompetitionBusinessSupplement(scenarioId.value))
    notice.value = '已补充，等待法务复核。'
  } catch {
    error.value = '提交失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}

onMounted(loadCenter)
</script>

<template>
  <div class="business-center">
    <header class="business-hero">
      <p class="business-eyebrow">AURORA BUSINESS DESK</p>
      <h1>Aurora 项目材料与补件中心</h1>
      <p>集中提交项目资料、确认事实并跟踪补件处理进度。</p>
      <span v-if="center" class="business-status">{{ center.current_status }}</span>
    </header>

    <div v-if="loading" class="business-loading">正在加载项目材料…</div>
    <p v-if="error" class="business-message business-message--error">{{ error }}</p>
    <p v-if="notice" class="business-message">{{ notice }}</p>

    <template v-if="center">
      <section class="business-section" aria-labelledby="business-materials-title">
        <div class="business-section__heading">
          <div><span>01</span><h2 id="business-materials-title">项目材料</h2></div>
          <button class="business-action" type="button" :disabled="busy" @click="projectFileInput?.click()">上传材料</button>
          <input ref="projectFileInput" class="business-file-input" type="file" @change="uploadMaterial('project', $event)" />
        </div>
        <div class="business-table-wrap">
          <table class="business-table">
            <thead><tr><th>文件名称</th><th>上传时间</th><th>处理状态</th></tr></thead>
            <tbody>
              <tr v-for="material in center.materials" :key="material.id">
                <td>{{ material.filename }}</td>
                <td>{{ new Date(material.uploaded_at).toLocaleString('zh-CN', { hour12: false }) }}</td>
                <td><span class="business-pill">{{ material.status }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="business-section" aria-labelledby="business-facts-title">
        <div class="business-section__heading">
          <div><span>02</span><h2 id="business-facts-title">事实确认</h2></div>
          <button class="business-action" type="button" :disabled="busy" @click="confirmFacts">确认事实</button>
        </div>
        <p class="business-section__intro">请按项目实际情况确认；需要更正时可直接修改后再次确认。</p>
        <div class="business-fact-grid">
          <label v-for="fact in center.facts" :key="fact.id" class="business-fact">
            <span>{{ fact.label }}</span>
            <input v-model="factDrafts[fact.id]" />
            <small>{{ fact.status }}</small>
          </label>
        </div>
      </section>

      <section class="business-section" aria-labelledby="business-supplements-title">
        <div class="business-section__heading">
          <div><span>03</span><h2 id="business-supplements-title">待补充信息</h2></div>
          <button class="business-action" type="button" :disabled="busy" @click="supplementFileInput?.click()">补充材料</button>
          <input ref="supplementFileInput" class="business-file-input" type="file" @change="uploadMaterial('supplement', $event)" />
        </div>
        <p class="business-section__intro">由于项目最终选址尚未确定，法务暂时无法完成部分许可路径判断。请上传选址说明或填写当前选址状态。</p>
        <div class="business-supplement-grid">
          <article v-for="item in center.supplements" :key="item.id" class="business-supplement">
            <div class="business-supplement__top"><h3>{{ item.title }}</h3><span>{{ item.status }}</span></div>
            <p><strong>为什么需要：</strong>{{ item.why }}</p>
            <p><strong>可接受材料：</strong>{{ item.accepted_materials.join('、') }}</p>
          </article>
        </div>
      </section>

      <section class="business-section" aria-labelledby="business-progress-title">
        <div class="business-section__heading">
          <div><span>04</span><h2 id="business-progress-title">处理进度</h2></div>
          <button class="business-action business-action--primary" type="button" :disabled="busy" @click="submitToLegal">提交法务</button>
        </div>
        <ol class="business-progress">
          <li v-for="step in center.progress" :key="step.label" :class="`business-progress--${step.state}`">
            <i aria-hidden="true"></i><span>{{ step.label }}</span>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<style scoped>
.business-center { max-width: 1220px; margin: 0 auto; padding: 36px 28px 64px; color: #15352f; }
.business-hero { position: relative; overflow: hidden; padding: 34px 38px; border: 1px solid #cfe0da; border-radius: 24px; background: linear-gradient(125deg, #f7fbf8 0%, #e4f1eb 100%); box-shadow: 0 18px 50px rgba(35, 82, 69, .08); }
.business-hero::after { content: ''; position: absolute; width: 260px; height: 260px; right: -80px; top: -120px; border-radius: 50%; background: rgba(92, 154, 132, .13); }
.business-eyebrow { margin: 0 0 9px; color: #50796d; font-size: 12px; font-weight: 800; letter-spacing: .15em; }
.business-hero h1 { margin: 0; font-size: clamp(28px, 4vw, 44px); line-height: 1.16; letter-spacing: -.035em; }
.business-hero > p:not(.business-eyebrow) { margin: 12px 0 0; color: #58736b; }
.business-status { display: inline-flex; margin-top: 22px; padding: 7px 13px; border-radius: 999px; background: #fff; color: #276751; font-size: 13px; font-weight: 700; }
.business-section { margin-top: 22px; padding: 26px 28px; border: 1px solid #d9e5e0; border-radius: 18px; background: #fff; box-shadow: 0 10px 30px rgba(36, 70, 61, .055); }
.business-section__heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.business-section__heading > div { display: flex; align-items: baseline; gap: 12px; }
.business-section__heading span { color: #6a9587; font-size: 12px; font-weight: 800; letter-spacing: .12em; }
.business-section h2 { margin: 0; font-size: 21px; }
.business-section__intro { margin: 12px 0 20px; color: #60766f; line-height: 1.7; }
.business-action { flex: 0 0 auto; padding: 10px 17px; border: 1px solid #2e765f; border-radius: 10px; background: #fff; color: #24624f; font: inherit; font-size: 14px; font-weight: 700; cursor: pointer; }
.business-action:hover { background: #eef7f2; }
.business-action:disabled { cursor: wait; opacity: .55; }
.business-action--primary { background: #286f58; color: #fff; }
.business-action--primary:hover { background: #205d49; }
.business-file-input { display: none; }
.business-table-wrap { margin-top: 20px; overflow-x: auto; }
.business-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.business-table th { padding: 0 14px 10px; color: #72867f; font-size: 12px; text-align: left; }
.business-table td { padding: 16px 14px; border-top: 1px solid #edf2ef; }
.business-pill { display: inline-flex; padding: 5px 10px; border-radius: 999px; background: #eaf5ef; color: #286b56; font-size: 12px; font-weight: 700; }
.business-fact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.business-fact { display: grid; grid-template-columns: minmax(90px, .45fr) 1fr auto; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 12px; background: #f6f9f7; }
.business-fact > span { color: #516d64; font-size: 13px; font-weight: 700; }
.business-fact input { min-width: 0; padding: 9px 10px; border: 1px solid #cfddd7; border-radius: 8px; background: #fff; color: #183d33; font: inherit; }
.business-fact small { color: #37745f; white-space: nowrap; }
.business-supplement-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.business-supplement { padding: 18px; border: 1px solid #e1e9e5; border-radius: 14px; background: #fbfcfb; }
.business-supplement__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.business-supplement h3 { margin: 0; font-size: 16px; }
.business-supplement__top span { flex: 0 0 auto; color: #9a681f; font-size: 12px; font-weight: 700; }
.business-supplement p { margin: 13px 0 0; color: #60736d; font-size: 13px; line-height: 1.65; }
.business-progress { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0; margin: 28px 0 6px; padding: 0; list-style: none; }
.business-progress li { position: relative; display: grid; justify-items: center; gap: 10px; color: #8a9994; font-size: 12px; text-align: center; }
.business-progress li::before { content: ''; position: absolute; top: 6px; left: 0; width: 100%; height: 2px; background: #e1e8e5; }
.business-progress i { z-index: 1; width: 14px; height: 14px; border: 3px solid #fff; border-radius: 50%; background: #ccd8d3; box-shadow: 0 0 0 1px #ccd8d3; }
.business-progress--completed, .business-progress--current { color: #296b56 !important; font-weight: 700; }
.business-progress--completed::before, .business-progress--current::before { background: #78ad99 !important; }
.business-progress--completed i, .business-progress--current i { background: #2e785f; box-shadow: 0 0 0 1px #2e785f; }
.business-progress--current i { box-shadow: 0 0 0 4px #dceee6; }
.business-message, .business-loading { margin: 18px 0 0; padding: 12px 16px; border-radius: 10px; background: #eaf5ef; color: #24624f; }
.business-message--error { background: #fff1ef; color: #9b3e31; }
@media (max-width: 800px) {
  .business-center { padding: 20px 14px 40px; }
  .business-hero, .business-section { padding: 22px 18px; }
  .business-fact-grid, .business-supplement-grid { grid-template-columns: 1fr; }
  .business-fact { grid-template-columns: 1fr; }
  .business-progress { grid-template-columns: 1fr; gap: 15px; justify-items: start; }
  .business-progress li { grid-template-columns: 18px 1fr; justify-items: start; text-align: left; }
  .business-progress li::before { display: none; }
}
</style>
