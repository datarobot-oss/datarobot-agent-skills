import type { Plugin } from "@opencode-ai/plugin"
import { Effect } from "effect"
import { cpSync, existsSync, mkdirSync, readdirSync } from "fs"
import { homedir } from "os"
import { dirname, join, resolve } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const BUNDLED_SKILLS = resolve(__dirname, "..", "skills")
const BUNDLED_PACKAGES = resolve(__dirname, "..", "packages")
const BUNDLED_THEMES_DIR = resolve(__dirname, "themes")

function getConfigDir(): string {
  if (process.env.XDG_CONFIG_HOME) {
    return process.env.XDG_CONFIG_HOME
  }
  return join(homedir(), ".config")
}

function installSkills(configDir: string): number {
  const targetDir = join(configDir, "opencode", "skills")
  mkdirSync(targetDir, { recursive: true })

  const skills = readdirSync(BUNDLED_SKILLS, { withFileTypes: true })
    .filter((d) => d.isDirectory())
  let installed = 0
  for (const skill of skills) {
    const dest = join(targetDir, skill.name)
    cpSync(join(BUNDLED_SKILLS, skill.name), dest, { recursive: true, force: true })
    installed++
  }
  return installed
}

function installPackages(configDir: string): void {
  // Copied next to skills/ so the skills' _bootstrap.py shim finds them.
  if (!existsSync(BUNDLED_PACKAGES)) {
    return
  }
  const targetDir = join(configDir, "opencode", "packages")
  cpSync(BUNDLED_PACKAGES, targetDir, { recursive: true, force: true })
}

function installThemes(configDir: string): number {
  const themesDir = join(configDir, "opencode", "themes")
  mkdirSync(themesDir, { recursive: true })

  const themes = readdirSync(BUNDLED_THEMES_DIR).filter((f) => f.endsWith(".json"))
  for (const theme of themes) {
    cpSync(join(BUNDLED_THEMES_DIR, theme), join(themesDir, theme))
  }
  return themes.length
}

function install(): string {
  const configDir = getConfigDir()
  const skillsInstalled = installSkills(configDir)
  installPackages(configDir)
  const themesInstalled = installThemes(configDir)
  return `Installed ${skillsInstalled} skills${themesInstalled > 0 ? ` and ${themesInstalled} DataRobot theme(s)` : ""}`
}

// One default export for both OpenCode generations: 1.x reads `server`, 2.x reads `id` + `effect`
// and ignores the rest.
export default {
  id: "opencode-datarobot-skills",
  server: (async ({ client }) => {
    await client.app.log({
      body: { service: "opencode-datarobot-skills", level: "info", message: install() },
    })
    return {}
  }) satisfies Plugin,
  effect: () => Effect.sync(install).pipe(Effect.flatMap((message) => Effect.logInfo(message))),
}
