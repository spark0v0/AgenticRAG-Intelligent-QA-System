import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import '@fontsource-variable/noto-sans-sc/wght.css'
import './styles/main.scss'

createApp(App).use(createPinia()).use(router).mount('#app')
