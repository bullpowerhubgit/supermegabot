import { tool } from "@opencode-ai/plugin"
import { readdir, stat } from "fs/promises"
import { join, relative, extname } from "path"

async function walk(dir: string, base: string): Promise<string[]> {
  const files: string[] = []
  const entries = await readdir(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...await walk(fullPath, base))
    } else if (entry.isFile()) {
      files.push(relative(base, fullPath))
    }
  }
  return files
}

export default tool({
  description: "Get project statistics: file counts, lines of code, module breakdown",
  args: {
    detail: tool.schema.enum(["summary", "modules", "full"]).describe("Level of detail").optional(),
  },
  async execute(args, context) {
    const detail = args.detail || "summary"
    const { worktree } = context

    const allFiles = await walk(worktree, worktree)

    const tsFiles = allFiles.filter(f => f.startsWith("src/") && f.endsWith(".ts"))
    const jsFiles = allFiles.filter(f => f.startsWith("src/") && f.endsWith(".js"))
    const htmlFiles = allFiles.filter(f => f.endsWith(".html") && !f.includes("/"))
    const scriptFiles = allFiles.filter(f => f.startsWith("scripts/") && (f.endsWith(".py") || f.endsWith(".sh") || f.endsWith(".js")))

    const totalSrc = tsFiles.length + jsFiles.length

    if (detail === "summary") {
      return `Project Stats (${worktree}):
  TypeScript: ${tsFiles.length} files
  JavaScript: ${jsFiles.length} files
  HTML: ${htmlFiles.length} files
  Scripts: ${scriptFiles.length} files
  Total src: ${totalSrc} files`
    }

    const coreFiles = tsFiles.filter(f => f.startsWith("src/core/"))
    const apiFiles = tsFiles.filter(f => f.startsWith("src/api/"))
    const cliFiles = tsFiles.filter(f => f.startsWith("src/cli/"))
    const extFiles = tsFiles.filter(f => f.startsWith("src/extension/"))

    return `Project Stats (${worktree}):
  TypeScript: ${tsFiles.length} files
  JavaScript: ${jsFiles.length} files
  HTML: ${htmlFiles.length} files
  Scripts: ${scriptFiles.length} files

  Modules:
    core/: ${coreFiles.length} files
    api/: ${apiFiles.length} files
    cli/: ${cliFiles.length} files
    extension/: ${extFiles.length} files`
  },
})
