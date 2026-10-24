const ContestList = () => import('./ContestList.vue')
const ContestDetails = () => import('./ContestDetail.vue')
const ContestProblemList = () => import('./children/ContestProblemList.vue')
const ContestRank = () => import('./children/ContestRank.vue')
const ACMContestHelper = () => import('./children/ACMHelper.vue')
const ContestPrepProblems = () => import('./children/ContestPrepProblems.vue')
const ContestPrepProblemEdit = () => import('./children/ContestPrepProblemEdit.vue')
const ContestPrepRoles = () => import('./children/ContestPrepRoles.vue')

export {
  ContestDetails, ContestList, ContestProblemList, ContestRank, ACMContestHelper,
  ContestPrepProblems, ContestPrepProblemEdit, ContestPrepRoles
}
