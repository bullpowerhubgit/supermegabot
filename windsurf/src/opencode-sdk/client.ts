import { createOpencode, createOpencodeClient } from "@opencode-ai/sdk"

/**
 * OpenCode SDK Client fuer programmatische Steuerung.
 *
 * Option 1: Server + Client starten
 * Option 2: Nur Client (Server laeuft bereits)
 */

export async function startServerAndClient() {
  const { client, server } = await createOpencode({
    hostname: "127.0.0.1",
    port: 4096,
    config: {
      model: "anthropic/claude-sonnet-4-20250514",
    },
  })

  console.log(`OpenCode Server running at ${server.url}`)

  // Server sauber beenden
  // server.close()

  return { client, server }
}

export function createClientOnly(baseUrl = "http://localhost:4096") {
  return createOpencodeClient({ baseUrl })
}

/**
 * Beispiel: Session erstellen und Prompt senden
 */
export async function exampleSession(client: Awaited<ReturnType<typeof createClientOnly>>) {
  const session = await client.session.create({
    body: { title: "API Integration Review" },
  })

  const sessionId = (session as any).id || 'unknown'
  console.log(`Session created: ${sessionId}`)

  const result = await client.session.prompt({
    path: { id: sessionId },
    body: {
      parts: [{ type: "text", text: "Review the src/core/ directory for best practices" }],
    },
  })

  return result
}

/**
 * Beispiel: Strukturierte JSON-Ausgabe
 */
export async function structuredOutputExample(
  client: Awaited<ReturnType<typeof createClientOnly>>,
  sessionId: string
) {
  const result = await client.session.prompt({
    path: { id: sessionId },
    body: {
      parts: [{ type: "text", text: "Analyze project structure" }],
      format: {
        type: "json_schema",
        schema: {
          type: "object",
          properties: {
            techStack: { type: "string" },
            modules: { type: "array", items: { type: "string" } },
            dependencies: { type: "number" },
          },
          required: ["techStack", "modules"],
        },
      },
    } as any,
  })

  return (result as any).data?.info?.structured_output
}

/**
 * Beispiel: Dateioperationen via SDK
 */
export async function fileOperationsExample(
  client: Awaited<ReturnType<typeof createClientOnly>>
) {
  // Suchen nach TypeScript Dateien
  const files = await client.find.files({
    query: { query: "*.ts" } as any,
  })

  // Text in Dateien suchen
  const textResults = await client.find.text({
    query: { pattern: "export async function" },
  })

  // Datei lesen
  const content = await client.file.read({
    query: { path: "package.json" },
  })

  return { files, textResults, content }
}
