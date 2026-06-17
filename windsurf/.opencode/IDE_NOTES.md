# OpenCode IDE Integration Notes

## Expected TypeScript Errors

### Missing `@opencode-ai/plugin` Module

**Error:** `Cannot find module '@opencode-ai/plugin' or its corresponding type declarations.`

**Files affected:**
- `.opencode/tools/platform-check.ts`
- `.opencode/tools/project-stats.ts`

**Explanation:** This is expected. The `@opencode-ai/plugin` package is provided by the OpenCode runtime, not installed in your project. These custom tools are loaded and executed by OpenCode itself, which provides the necessary types at runtime.

**Action:** Ignore these errors. The tools will work correctly when OpenCode loads them.

### Missing `@opencode-ai/sdk` Module

**Error:** `Cannot find module '@opencode-ai/sdk' or its corresponding type declarations.`

**Files affected:**
- `src/opencode-sdk/client.ts`

**Explanation:** This error occurs before the package is installed. After running `npm install @opencode-ai/sdk@1.16.2`, this error should resolve.

**Action:** Run `npm install` to install the SDK.

### Implicit `any` Types

**Error:** `Parameter 'args' implicitly has an 'any' type.`

**Files affected:**
- `.opencode/tools/platform-check.ts`
- `.opencode/tools/project-stats.ts`

**Explanation:** OpenCode's tool runtime provides type information for the `args` and `context` parameters. The TypeScript compiler doesn't have access to these runtime types.

**Action:** Ignore these errors. OpenCode validates the types at runtime.

## VS Code Schema Warnings

### Untrusted Schema Location

**Error:** `Unable to load schema from 'https://opencode.ai/config.json': Location https://opencode.ai/config.json is untrusted.`

**Files affected:**
- `opencode.json`
- `tui.json`

**Explanation:** VS Code doesn't trust the OpenCode schema URL by default. This is a security feature of VS Code. The schema is used for validation and autocomplete but is not required for OpenCode to function.

**Action:** Either:
1. Ignore the warning (OpenCode works without it)
2. Add the URL to VS Code's trusted schemas in settings:
   ```json
   {
     "json.schemaTrusted": [
       {
         "pattern": "opencode.json",
         "url": "https://opencode.ai/config.json"
       },
       {
         "pattern": "tui.json",
         "url": "https://opencode.ai/tui.json"
       }
     ]
   }
   ```

## OpenCode Binary

### Not Installed

**Status:** OpenCode CLI is not currently installed on this system.

**Action:** Install OpenCode from https://opencode.ai/install

After installation, the `acp.json` configuration will work with JetBrains IDEs and other ACP-compatible editors.

## Summary

All IDE errors and warnings are cosmetic or expected. OpenCode's runtime provides the necessary types and validation. The configuration files will work correctly when OpenCode is installed and running.
