// Advancing places or medals on a contest board. Contest admins give each tier
// a count or a percentage of the official places; a percentage floors to whole
// places, and the tiers follow one another down the board.
export const AWARD_MODES = Object.freeze({
  advance: [['advance', '晋级']],
  medal: [['gold', '金牌'], ['silver', '银牌'], ['bronze', '铜牌']]
})

// Floating point makes 2.3% of 1000 come out as 22.999…; the epsilon keeps an
// exact product whole before it is floored.
export function percentCount (percent, official) {
  return Math.floor(Math.max(0, Number(percent) || 0) * official / 100 + 1e-9)
}

// The share a count takes, to two decimals, for showing next to it.
export function countPercent (count, official) {
  return official ? Math.round(Math.max(0, Number(count) || 0) / official * 10000) / 100 : 0
}

function tierCount (setting, official) {
  const count = setting.kind === 'percent' ? percentCount(setting.value, official) : Math.floor(Number(setting.value) || 0)
  return Math.max(0, count)
}

// The tiers in use as { key, label, count, last }: a tier holds the `count`
// official places that end at place `last`. Places past the board get none.
export function awardRanges (awards, official) {
  const tiers = (awards && AWARD_MODES[awards.mode]) || []
  let last = 0
  return tiers.filter(([key]) => awards.tiers && awards.tiers[key]).map(([key, label]) => {
    const count = Math.min(tierCount(awards.tiers[key], official), official - last)
    last += count
    return { key, label, count, last }
  })
}

export function placeTier (place, ranges) {
  if (!Number.isInteger(place) || place < 1) return null
  return ranges.find(range => range.count > 0 && place <= range.last) || null
}
