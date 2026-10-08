import { createRouter, createWebHistory } from 'vue-router'

const Home = () => import('./views/Home.vue')
const Login = () => import('./views/general/Login.vue')
const Dashboard = () => import('./views/general/Dashboard.vue')
const Announcement = () => import('./views/general/Announcement.vue')
const User = () => import('./views/general/User.vue')
const JudgeServer = () => import('./views/general/JudgeServer.vue')
const PruneTestCase = () => import('./views/general/PruneTestCase.vue')
const Problem = () => import('./views/problem/Problem.vue')
const ProblemList = () => import('./views/problem/ProblemList.vue')
const ProblemImportOrExport = () => import('./views/problem/ImportAndExport.vue')
const Contest = () => import('./views/contest/Contest.vue')
const ContestList = () => import('./views/contest/ContestList.vue')

export default createRouter({
  history: createWebHistory('/admin/'),
  scrollBehavior: () => ({top: 0}),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: Login
    },
    {
      path: '/',
      component: Home,
      children: [
        { path: '/ai/problems', name: 'ai-problems', component: () => import('./views/ai/Problems.vue') },
        { path: '/ai/problem/batch_ops', name: 'ai-problem-batch-ops', component: ProblemImportOrExport },
        {
          path: '',
          name: 'dashboard',
          component: Dashboard
        },
        {
          path: '/announcement',
          name: 'announcement',
          component: Announcement
        },
        {
          path: '/user',
          name: 'user',
          component: User
        },
        {
          path: '/judge-server',
          name: 'judge-server',
          component: JudgeServer
        },
        {
          path: '/prune-test-case',
          name: 'prune-test-case',
          component: PruneTestCase
        },
        {
          path: '/problems',
          name: 'problem-list',
          component: ProblemList
        },
        {
          path: '/problem/create',
          name: 'create-problem',
          component: Problem
        },
        {
          path: '/problem/edit/:problemId',
          name: 'edit-problem',
          component: Problem
        },
        {
          path: '/problem/batch_ops',
          name: 'problem_batch_ops',
          component: ProblemImportOrExport
        },
        {
          path: '/contest/create',
          name: 'create-contest',
          component: Contest
        },
        {
          path: '/contest',
          name: 'contest-list',
          component: ContestList
        },
        {
          path: '/contest/:contestId/edit',
          name: 'edit-contest',
          component: Contest
        },
        {
          path: '/contest/:contestId/announcement',
          name: 'contest-announcement',
          component: Announcement
        },
        {
          path: '/contest/:contestId/problems',
          name: 'contest-problem-list',
          component: ProblemList
        },
        {
          path: '/contest/:contestId/problem/create',
          name: 'create-contest-problem',
          component: Problem
        },
        {
          path: '/contest/:contestId/problem/:problemId/edit',
          name: 'edit-contest-problem',
          component: Problem
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*', redirect: '/login'
    }
  ]
})
