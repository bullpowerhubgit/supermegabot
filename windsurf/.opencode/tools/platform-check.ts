import { tool } from "@opencode-ai/plugin"
import { readFile } from "fs/promises"

export default tool({
  description: "Check platform account creation progress from HTML files",
  args: {
    file: tool.schema.enum(["platform-links-20.html", "platform-links.html", "remaining-platforms.html", "all"])
      .describe("Which HTML file to check, or 'all' for summary")
      .optional(),
  },
  async execute(args) {
    const target = args.file || "all"
    const results: Record<string, any> = {}

    const files = [
      { path: "platform-links-20.html", name: "Top 21" },
      { path: "platform-links.html", name: "Full List" },
      { path: "remaining-platforms.html", name: "All 63" },
    ]

    for (const { path, name } of files) {
      if (target !== "all" && !path.includes(target.replace(".html", ""))) continue

      try {
        const content = await readFile(path, "utf-8")
        const total = (content.match(/class="status/g) || []).length
        const done = (content.match(/class="status done"/g) || []).length
        const pending = total - done

        results[name] = { total, done, pending, file: path }
      } catch {
        results[name] = { error: "File not found", file: path }
      }
    }

    if (target === "all") {
      const totalDone = Object.values(results).reduce((sum: number, r: any) => sum + (r.done || 0), 0)
      const totalPlatforms = Object.values(results).reduce((sum: number, r: any) => sum + (r.total || 0), 0)
      return `Platform Account Creation Progress:\n${Object.entries(results)
        .map(([name, r]: [string, any]) => `  ${name}: ${r.done || 0}/${r.total || 0} done`)
        .join("\n")}\n\nOverall: ${totalDone}/${totalPlatforms} platforms completed`
    }

    const r = Object.values(results)[0] as any
    return `${r.file}: ${r.done}/${r.total} done, ${r.pending} pending`
  },
})
