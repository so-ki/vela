#!/usr/bin/env node

import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { createRequire } from 'node:module'

const requireFromFrontend = createRequire(
  new URL('../../frontend/package.json', import.meta.url),
)
const { chromium } = requireFromFrontend('playwright')

const MAX_SOURCE_BYTES = 25 * 1024 * 1024
const ALLOWED_HOST = 'www.al.sp.gov.br'

function parseArgs(argv) {
  const args = new Map()
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || !value) {
      throw new Error('expected --targets <path> --output-dir <path>')
    }
    args.set(key, value)
  }
  if (!args.has('--targets') || !args.has('--output-dir')) {
    throw new Error('expected --targets <path> --output-dir <path>')
  }
  return {
    targetsPath: path.resolve(args.get('--targets')),
    outputDir: path.resolve(args.get('--output-dir')),
  }
}

function validateTarget(target) {
  if (!/^[a-z0-9-]+$/.test(target.id || '')) {
    throw new Error(`unsafe target id: ${target.id}`)
  }
  const url = new URL(target.document_url)
  if (url.protocol !== 'https:' || url.hostname !== ALLOWED_HOST) {
    throw new Error(`non-official target URL: ${target.document_url}`)
  }
  if (!['official_html_rendered_pdf', 'official_native_pdf'].includes(target.source_type)) {
    throw new Error(`unsupported source type: ${target.source_type}`)
  }
}

async function fetchBoundedPdf(url) {
  const response = await fetch(url, {
    redirect: 'follow',
    signal: AbortSignal.timeout(60_000),
    headers: { 'User-Agent': 'Vela-Ingestion-QA/1.0 (official-source verification)' },
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`)
  }
  const declaredLength = Number(response.headers.get('content-length') || 0)
  if (declaredLength > MAX_SOURCE_BYTES) {
    throw new Error(`official PDF exceeds ${MAX_SOURCE_BYTES} bytes`)
  }
  const bytes = Buffer.from(await response.arrayBuffer())
  if (bytes.length > MAX_SOURCE_BYTES || !bytes.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
    throw new Error('native source is oversized or not a PDF')
  }
  return bytes
}

async function gotoWithRetry(page, url) {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await page.goto(url, {
        timeout: 60_000,
        waitUntil: 'domcontentloaded',
      })
      if (!response || !response.ok()) {
        throw new Error(`HTTP ${response?.status() ?? 'no response'} for ${url}`)
      }
      await page.waitForSelector('body', { timeout: 10_000 })
      await page.evaluate(() => document.fonts?.ready)
      return
    } catch (error) {
      lastError = error
      if (attempt < 3) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 1_000))
      }
    }
  }
  throw lastError
}

async function main() {
  const { targetsPath, outputDir } = parseArgs(process.argv.slice(2))
  const config = JSON.parse(await fs.readFile(targetsPath, 'utf8'))
  await fs.mkdir(outputDir, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ locale: 'pt-BR' })
  const results = []
  try {
    for (const target of config.targets) {
      validateTarget(target)
      const outputPath = path.join(outputDir, `${target.id}.pdf`)
      let pdfBytes
      let sourceTextSha256 = null
      let sourceTextCharacters = null

      if (target.source_type === 'official_native_pdf') {
        pdfBytes = await fetchBoundedPdf(target.document_url)
        await fs.writeFile(outputPath, pdfBytes, { mode: 0o600 })
      } else {
        const page = await context.newPage()
        try {
          await gotoWithRetry(page, target.document_url)
          const sourceText = (await page.locator('body').innerText()).trim()
          if (sourceText.length < 200) {
            throw new Error(`official HTML body too short: ${sourceText.length} characters`)
          }
          sourceTextCharacters = sourceText.length
          sourceTextSha256 = crypto.createHash('sha256').update(sourceText).digest('hex')
          await fs.writeFile(
            path.join(outputDir, `${target.id}.source.txt`),
            sourceText,
            { mode: 0o600 },
          )
          await page.emulateMedia({ media: 'screen' })
          pdfBytes = await page.pdf({
            path: outputPath,
            format: 'A4',
            printBackground: true,
            preferCSSPageSize: true,
          })
        } finally {
          await page.close()
        }
      }

      const onDisk = await fs.readFile(outputPath)
      if (onDisk.length > MAX_SOURCE_BYTES || !onDisk.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
        throw new Error(`rendered output for ${target.id} is oversized or not a PDF`)
      }
      results.push({
        id: target.id,
        source_type: target.source_type,
        output_filename: `${target.id}.pdf`,
        pdf_bytes: onDisk.length,
        pdf_sha256: crypto.createHash('sha256').update(onDisk).digest('hex'),
        source_text_characters: sourceTextCharacters,
        source_text_sha256: sourceTextSha256,
        source_text_filename:
          target.source_type === 'official_html_rendered_pdf'
            ? `${target.id}.source.txt`
            : null,
      })
    }
  } finally {
    await context.close()
    await browser.close()
  }

  process.stdout.write(`${JSON.stringify({ results }, null, 2)}\n`)
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`)
  process.exitCode = 1
})
