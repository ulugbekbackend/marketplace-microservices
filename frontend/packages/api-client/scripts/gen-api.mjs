// Generates TypeScript types from every OpenAPI schema in ../openapi/<service>.json
// into ../src/generated/<service>.ts. Usage: pnpm gen-api
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const schemaDir = join(root, 'openapi')
const outDir = join(root, 'src', 'generated')

const schemas = (await readdir(schemaDir)).filter((file) => file.endsWith('.json')).sort()

if (schemas.length === 0) {
  console.log(`No OpenAPI schemas in ${schemaDir}; keeping the hand-written types in src/types.ts.`)
  process.exit(0)
}

await mkdir(outDir, { recursive: true })

for (const file of schemas) {
  const service = basename(file, '.json')
  const schema = JSON.parse(await readFile(join(schemaDir, file), 'utf8'))
  const ast = await openapiTS(schema, { exportType: true, alphabetize: true })
  const banner = `// Generated from openapi/${file} by scripts/gen-api.mjs. Do not edit.\n\n`
  await writeFile(join(outDir, `${service}.ts`), banner + astToString(ast))
  console.log(`generated src/generated/${service}.ts`)
}
