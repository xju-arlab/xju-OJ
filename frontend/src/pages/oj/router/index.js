import { createRouter, createWebHistory } from 'vue-router'
import { recoverFromStaleChunks } from '@/utils/chunkRecovery'
import routes from './routes'
import storage from '@/utils/storage'
import { STORAGE_KEY } from '@/utils/constants'
import store, { types, setStoreRouter } from '@/store'

const router = createRouter({
  history: createWebHistory('/'),
  scrollBehavior (to, from, savedPosition) { return savedPosition || { left: 0, top: 0 } },
  routes
})
setStoreRouter(router)

router.beforeEach(to => {
  if (to.matched.some(record => record.meta.requiresAuth) && !storage.get(STORAGE_KEY.AUTHED)) {
    store.commit(types.CHANGE_MODAL_STATUS, { mode: 'login', visible: true })
    // Preserve an OIDC failure code while redirecting so the app can explain
    // the sign-in failure instead of dropping it with the query string.
    const query = to.query.auth_error ? { auth_error: to.query.auth_error } : undefined
    return { name: 'home', query }
  }
})

recoverFromStaleChunks(router)

export default router
