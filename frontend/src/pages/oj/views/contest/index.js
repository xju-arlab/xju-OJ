const ContestList = () => import('./ContestList.vue')
const ContestDetails = () => import('./ContestDetail.vue')
const ContestProblemList = () => import('./children/ContestProblemList.vue')
const ContestRank = () => import('./children/ContestRank.vue')
const ACMContestHelper = () => import('./children/ACMHelper.vue')
const ContestPrepProblems = () => import('./children/ContestPrepProblems.vue')
const ContestPrepProblemEdit = () => import('./children/ContestPrepProblemEdit.vue')
const ContestPrepUpload = () => import('./children/ContestPrepUpload.vue')
const ContestPrepRoles = () => import('./children/ContestPrepRoles.vue')
const ContestPrepAssign = () => import('./children/ContestPrepAssign.vue')
// The review overview is drawn by ContestDetail itself; the route only needs a placeholder.
const ContestPrepReview = { name: 'ContestPrepReview', render: () => null }
const PrepInvite = () => import('./PrepInvite.vue')

export {
  ContestDetails, ContestList, ContestProblemList, ContestRank, ACMContestHelper,
  ContestPrepProblems, ContestPrepProblemEdit, ContestPrepUpload, ContestPrepRoles, ContestPrepAssign,
  ContestPrepReview, PrepInvite
}
