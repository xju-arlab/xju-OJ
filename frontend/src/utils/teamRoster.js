// Team rosters for contest team accounts: a CSV of team name and up to three
// members, and the account sheet handed back once with the passwords.
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

export function parseRoster (text, skipHeader) {
  const rows = papa.parse(text, { skipEmptyLines: 'greedy' }).data
    .map(cells => cells.map(cell => String(cell ?? '').trim()))
  return (skipHeader ? rows.slice(1) : rows).map((cells, index) => ({
    line: index + (skipHeader ? 2 : 1),
    name: cells[0] || '',
    members: cells.slice(1, 4).filter(Boolean)
  }))
}

// Problems the server would also reject, reported per CSV line.
export function rosterErrors (teams, existingNames = []) {
  const errors = []
  const seen = new Set(existingNames)
  for (const team of teams) {
    if (!team.name) errors.push(`第 ${team.line} 行缺少队伍名`)
    else if (team.name.length > TEAM_NAME_MAX) errors.push(`第 ${team.line} 行队伍名超过 ${TEAM_NAME_MAX} 字`)
    else if (seen.has(team.name)) errors.push(`第 ${team.line} 行队伍名「${team.name}」重复`)
    if (team.members.some(member => member.length > MEMBER_NAME_MAX)) errors.push(`第 ${team.line} 行队员名超过 ${MEMBER_NAME_MAX} 字`)
    seen.add(team.name)
  }
  if (teams.length > 500) errors.push('一次最多导入 500 支队伍')
  return errors
}

function csvCell (value) {
  let text = String(value ?? '')
  // Keep spreadsheet programs from running a cell as a formula.
  if (/^[=+\-@\t\r]/.test(text)) text = "'" + text
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text
}

export function downloadTeamAccounts (filename, teams) {
  const lines = [['队伍名', '队员1', '队员2', '队员3', '用户名', '密码']]
  for (const team of teams) {
    const members = [...team.members, '', '', ''].slice(0, 3)
    lines.push([team.name, ...members, team.username, team.password])
  }
  // The BOM lets Excel read the sheet as UTF-8.
  const blob = new Blob(['﻿' + lines.map(line => line.map(csvCell).join(',')).join('\r\n')],
    { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
