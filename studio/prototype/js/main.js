import { boot } from './app.js'

boot(document.getElementById('studio')).catch(err => {
  window.__h64 = window.__h64 || { errors: [] }
  window.__h64.errors.push(String(err && err.stack ? err.stack : err))
})
