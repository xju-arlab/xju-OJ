// Team rosters for contest team accounts: a CSV of team name, up to three
// members, an optional team type and campus, and the account sheet handed back
// once with the passwords.
import axios from 'axios'
import papa from 'papaparse'

export const TEAM_NAME_MAX = 64
export const MEMBER_NAME_MAX = 32

// Excel on Chinese Windows saves CSV as GBK unless "CSV UTF-8" is chosen.
export async function readRosterText (file) {
  const buffer = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer)
  } catch (_) {
    return new TextDecoder('gb18030').decode(buffer)
  }
}

export function looksLikeHeader (cells) {
  const [name = '', first = ''] = cells.map(cell => String(cell).trim())
  return /^(队伍名称?|队名|队伍|team( name)?|name)$/i.test(name) || /^(队员|成员|member)\s*1?$/i.test(first)
}

// A team without a name is called after its members' surnames: 赵某、孙某 → 赵孙队.
export function surnameTeamName (members, taken) {
  const base = members.map(member => Array.from(member)[0]).join('') + '队'
  let name = base
  for (let index = 2; taken.has(name); index++) name = base + index
  return name
}

// The fifth column: 正式队伍 when left out, or 打星队伍; null for anything else.
export function teamIsStar (kind) {
  if (/^(正式(队伍?)?|official)?$/i.test(kind)) return false
  if (/^(打星(队伍?)?|[*★]|star)$/i.test(kind)) return true
  return null
}

export const CAMPUSES = Object.freeze({ boda: '博达校区', youhao: '友好校区' })

// The sixth column: a campus by its full or short name, '' when blank; null for anything else.
export function teamCampus (text) {
  if (!text) return ''
  const code = Object.keys(CAMPUSES).find(key => text === CAMPUSES[key] || text === CAMPUSES[key].replace('校区', ''))
  return code || null
}

// A row is a team the contest already has when it names that team, or, left
// unnamed, holds all the members of exactly one existing team.
function existingTeamFor (row, existingTeams) {
  if (row.name) return existingTeams.find(team => team.name === row.name)
  const holding = existingTeams.filter(team => team.members.length && team.members.every(member => row.members.includes(member)))
  return holding.length === 1 ? holding[0] : undefined
}

// What a row adds to its existing team: members it extends and a campus it lacks.
// Anything that contradicts the team is left alone and listed as a conflict.
export function teamSupplement (row, team) {
  const changes = {}
  const conflicts = []
  const extendsMembers = row.members.length > team.members.length && team.members.every(member => row.members.includes(member))
  if (extendsMembers) changes.members = row.members
  else if (row.members.some(member => !team.members.includes(member))) conflicts.push('队员')
  if (row.campus && !team.campus) changes.campus = row.campus
  else if (row.campus && row.campus !== team.campus) conflicts.push('校区')
  if (row.kind && row.star !== null && row.star !== Boolean(team.star)) conflicts.push('队伍类型')
  return { changes, conflicts }
}

export function parseRoster (text, skipHeader, existingTeams = []) {
  const rows = papa.parse(text, { skipEmptyLines: 'greedy' }).data
    .map(cells => cells.map(cell => String(cell ?? '').trim()))
  const teams = (skipHeader ? rows.slice(1) : rows).map((cells, index) => ({
    line: index + (skipHeader ? 2 : 1),
    name: cells[0] || '',
    members: cells.slice(1, 4).filter(Boolean),
    kind: cells[4] || '',
    star: teamIsStar(cells[4] || ''),
    campusText: cells[5] || '',
    campus: teamCampus(cells[5] || '')
  })).filter(team => team.name || team.members.length)
  for (const team of teams) {
    team.existing = existingTeamFor(team, existingTeams)
    if (!team.existing) continue
    team.name = team.existing.name
    Object.assign(team, teamSupplement(team, team.existing))
  }
  const taken = new Set([...existingTeams.map(team => team.name), ...teams.map(team => team.name).filter(Boolean)])
  for (const team of teams) {
    if (team.name) continue
    team.name = surnameTeamName(team.members, taken)
    team.derived = true
    taken.add(team.name)
  }
  return teams
}

// Problems the server would also reject, reported per CSV line. Rows for
// existing teams are no problem: they only fill those teams in.
export function rosterErrors (teams) {
  const errors = []
  const seen = new Set()
  for (const team of teams) {
    if (!team.name) errors.push(`第 ${team.line} 行缺少队伍名`)
    else if (team.name.length > TEAM_NAME_MAX) errors.push(`第 ${team.line} 行队伍名超过 ${TEAM_NAME_MAX} 字`)
    else if (seen.has(team.name)) errors.push(`第 ${team.line} 行队伍「${team.name}」重复`)
    if (team.members.some(member => member.length > MEMBER_NAME_MAX)) errors.push(`第 ${team.line} 行队员名超过 ${MEMBER_NAME_MAX} 字`)
    if (team.star === null) errors.push(`第 ${team.line} 行队伍类型「${team.kind}」应为正式队伍或打星队伍`)
    if (team.campus === null) errors.push(`第 ${team.line} 行校区「${team.campusText}」应为博达校区或友好校区`)
    seen.add(team.name)
  }
  if (teams.length > 500) errors.push('一次最多导入 500 支队伍')
  return errors
}

// The roster split into accounts to create and changes to existing teams.
export function rosterPlan (teams) {
  return {
    create: teams.filter(team => !team.existing).map(({ name, members, star, campus }) => ({ name, members, star, campus })),
    update: teams.filter(team => team.existing && Object.keys(team.changes).length)
      .map(team => ({ id: team.existing.id, name: team.name, ...team.changes }))
  }
}

function csvCell (value) {
  let text = String(value ?? '')
  // Keep spreadsheet programs from running a cell as a formula.
  if (/^[=+\-@\t\r]/.test(text)) text = "'" + text
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text
}

// The A4 slips to cut apart; the server typesets what it is sent and keeps nothing.
export async function downloadTeamSheet (contestId, link, teams) {
  const res = await axios.post('admin/contest/teams/sheet', {
    contest_id: contestId, link, teams: teams.map(({ name, members, username, password, star }) => ({ name, members, username, password, star }))
  }, { responseType: 'blob' })
  if (res.data.type !== 'application/pdf') {
    const body = JSON.parse(await res.data.text())
    throw new Error(typeof body.data === 'string' ? body.data : '导出 PDF 失败')
  }
  saveBlob(`contest-${contestId}-teams.pdf`, res.data)
}

function saveBlob (filename, blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadTeamAccounts (filename, teams) {
  // The first six columns read back as a roster.
  const lines = [['队伍名', '队员1', '队员2', '队员3', '队伍类型', '校区', '用户名', '密码']]
  for (const team of teams) {
    const members = [...team.members, '', '', ''].slice(0, 3)
    lines.push([team.name, ...members, team.star ? '打星队伍' : '正式队伍', CAMPUSES[team.campus] || '', team.username, team.password])
  }
  // The BOM lets Excel read the sheet as UTF-8.
  saveBlob(filename, new Blob(['\ufeff' + lines.map(line => line.map(csvCell).join(',')).join('\r\n')],
    { type: 'text/csv;charset=utf-8' }))
}
