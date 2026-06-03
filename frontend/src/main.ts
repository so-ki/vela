import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

app.config.errorHandler = (err, _instance, info) => {
  console.error('[Vela]', err, info)
  const root = document.getElementById('app')
  if (!root || root.querySelector('.boot-error')) return
  root.insertAdjacentHTML(
    'beforeend',
    `<div class="boot-error" style="padding:24px;font-family:sans-serif;color:#dc2626">
      <h2>页面加载出错</h2>
      <p>${String(err)}</p>
      <p style="color:#6b7280;font-size:14px">${info}</p>
    </div>`,
  )
}

app.mount('#app')
