import api from '@oj/api'

const unwrap = res => res.data.data

// ProblemEditorForm service for problems of a contest under preparation.
export function prepProblemService (contestID) {
  return {
    getLanguages: () => api.getLanguages().then(unwrap),
    getProblemTagList: params => api.getProblemTagList(params).then(unwrap),
    // The contest detail payload carries rule_type and prep_state.
    getContest: () => api.getContest(contestID).then(unwrap),
    getProblem: id => api.getPrepProblem(contestID, id).then(unwrap),
    compileSPJ: data => api.compilePrepSPJ({ ...data, contest_id: contestID }),
    saveProblem: (problem, mode) => {
      const payload = { ...problem, contest_id: contestID }
      return mode === 'edit' ? api.editPrepProblem(payload) : api.createPrepProblem(payload)
    },
    testCaseUploadAction: '/api/contest/prep/test_case',
    testCaseUploadData: { contest_id: contestID },
    imageUploadAction: '/api/contest/prep/upload_image',
    imageUploadData: { contest_id: contestID }
  }
}
