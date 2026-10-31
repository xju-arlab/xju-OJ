import { createRouter, createWebHistory } from 'vue-router'
import { recoverFromStaleChunks } from '@/utils/chunkRecovery'
import routes from './routes'
import storage from '@/utils/storage'
import { arenaContest } from '@/utils/arena'
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
  // A contest entered through its link stays on /arena/ URLs, whoever is
  // signed in; a team account always sees its own contest that way.
  const contest = /^\/contest\/(\d+)(\/.*)?$/.exec(to.path)
  if (contest) {
    const team = store.state.user.profile.team
    if (arenaContest() === contest[1] || (team && String(team.contest_id) === contest[1])) {
      return { path: `/arena/${contest[1]}${contest[2] || '/'}`, query: to.query, hash: to.hash }
    }
  }
})

recoverFromStaleChunks(router)

export default router
