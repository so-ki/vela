export type DiffSegmentKind = 'same' | 'unique'

export interface DiffSegment {
  text: string
  kind: DiffSegmentKind
}

export interface SegmentedConflictSource {
  filename: string
  value: string
  segments: DiffSegment[]
  uniqueCount: number
  fullyDifferent: boolean
}

function normalizeForCompare(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

/** 按句号、分号、换行等切分，便于标注差异片段 */
export function splitIntoDiffChunks(text: string): string[] {
  const trimmed = text.trim()
  if (!trimmed) return []

  const bySentence = trimmed.split(/(?<=[。！？；])\s*|\n+/).filter((part) => part.trim())
  if (bySentence.length > 1) return bySentence

  if (trimmed.length > 160) {
    const byClause = trimmed.split(/(?<=[，、：:])/).filter((part) => part.trim())
    if (byClause.length > 1) return byClause
  }

  return [trimmed]
}

function chunkAppearsInSource(chunk: string, source: string): boolean {
  const chunkNorm = normalizeForCompare(chunk)
  const sourceNorm = normalizeForCompare(source)
  if (!chunkNorm) return false
  if (chunkNorm.length < 6) return sourceNorm.includes(chunkNorm)
  return sourceNorm.includes(chunkNorm) || chunkNorm.includes(sourceNorm)
}

function chunkAppearsInOthers(chunk: string, others: string[]): boolean {
  return others.some((other) => chunkAppearsInSource(chunk, other))
}

function collectExclusiveParts(sources: Array<{ filename: string; value: string }>): string[] {
  const seen = new Set<string>()
  const parts: string[] = []

  for (let i = 0; i < sources.length; i++) {
    const others = sources.filter((_, j) => j !== i).map((source) => source.value)
    for (const segment of diffTextAgainstOthers(sources[i].value, others)) {
      if (segment.kind !== 'unique') continue
      const trimmed = segment.text.trim()
      if (trimmed.length < 4) continue
      const key = normalizeForCompare(trimmed)
      if (seen.has(key)) continue
      seen.add(key)
      parts.push(segment.text)
    }
  }

  return parts.sort((a, b) => b.length - a.length)
}

interface TextMark {
  start: number
  end: number
}

function mergeTextMarks(marks: TextMark[]): TextMark[] {
  if (!marks.length) return []
  const sorted = [...marks].sort((a, b) => a.start - b.start)
  const merged: TextMark[] = [{ ...sorted[0] }]
  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i]
    const last = merged[merged.length - 1]
    if (current.start <= last.end) {
      last.end = Math.max(last.end, current.end)
    } else {
      merged.push({ ...current })
    }
  }
  return merged
}

function markExclusiveRanges(text: string, exclusives: string[]): TextMark[] {
  const marks: TextMark[] = []
  for (const exclusive of exclusives) {
    if (!exclusive) continue
    let searchFrom = 0
    while (searchFrom < text.length) {
      const idx = text.indexOf(exclusive, searchFrom)
      if (idx === -1) break
      marks.push({ start: idx, end: idx + exclusive.length })
      searchFrom = idx + Math.max(1, exclusive.length)
    }
  }
  return mergeTextMarks(marks)
}

function segmentsFromMarks(text: string, marks: TextMark[]): DiffSegment[] {
  if (!marks.length) return []
  const segments: DiffSegment[] = []
  let pos = 0
  for (const mark of marks) {
    if (pos < mark.start) {
      segments.push({ text: text.slice(pos, mark.start), kind: 'same' })
    }
    segments.push({ text: text.slice(mark.start, mark.end), kind: 'unique' })
    pos = mark.end
  }
  if (pos < text.length) {
    segments.push({ text: text.slice(pos), kind: 'same' })
  }
  return segments
}

function segmentsBySourceCoverage(
  text: string,
  sources: Array<{ filename: string; value: string }>,
): DiffSegment[] {
  const sourceValues = sources.map((source) => source.value)
  return splitIntoDiffChunks(text).map((chunk) => {
    const matchCount = sourceValues.filter((source) => chunkAppearsInSource(chunk, source)).length
    return { text: chunk, kind: matchCount <= 1 ? ('unique' as const) : ('same' as const) }
  })
}

/** 合并字段当前值相对各文件抽取结果的冲突片段（用于编辑框内联标红） */
export function conflictSegmentsForFieldValue(
  currentValue: string,
  sources: Array<{ filename: string; value: string }>,
): DiffSegment[] {
  const text = currentValue || ''
  if (!text.trim()) return []
  if (sources.length < 2) return [{ text, kind: 'same' }]

  const exclusives = collectExclusiveParts(sources)
  const marked = segmentsFromMarks(text, markExclusiveRanges(text, exclusives))
  if (marked.some((segment) => segment.kind === 'unique')) {
    return marked
  }

  const byCoverage = segmentsBySourceCoverage(text, sources)
  if (byCoverage.some((segment) => segment.kind === 'unique')) {
    return byCoverage
  }

  return [{ text, kind: 'unique' as const }]
}

export function diffTextAgainstOthers(text: string, others: string[]): DiffSegment[] {
  const chunks = splitIntoDiffChunks(text)
  if (!chunks.length) return []

  if (others.every((other) => !other.trim())) {
    return chunks.map((chunk) => ({ text: chunk, kind: 'unique' as const }))
  }

  return chunks.map((chunk) => ({
    text: chunk,
    kind: chunkAppearsInOthers(chunk, others) ? 'same' : 'unique',
  }))
}

export function segmentConflictSources(
  sources: Array<{ filename: string; value: string }>,
): SegmentedConflictSource[] {
  return sources.map((source, index) => {
    const others = sources.filter((_, i) => i !== index).map((item) => item.value)
    const segments = diffTextAgainstOthers(source.value, others)
    const uniqueCount = segments.filter((segment) => segment.kind === 'unique').length
    const fullyDifferent = segments.length > 0 && uniqueCount === segments.length
    return {
      filename: source.filename,
      value: source.value,
      segments,
      uniqueCount,
      fullyDifferent,
    }
  })
}

export function uniqueExcerpt(text: string, others: string[], maxLen = 72): string | null {
  const segments = diffTextAgainstOthers(text, others)
    .filter((segment) => segment.kind === 'unique')
    .map((segment) => segment.text.trim())
    .filter(Boolean)
  if (!segments.length) return null
  const joined = segments.join('')
  if (joined.length <= maxLen) return joined
  return `${joined.slice(0, maxLen)}…`
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function buildConflictHighlightHtml(segments: DiffSegment[]): string {
  return segments
    .map((segment) => {
      const escaped = escapeHtml(segment.text)
      if (segment.kind === 'unique') {
        return `<span class="conflict-inline-unique">${escaped}</span>`
      }
      return escaped
    })
    .join('')
}
