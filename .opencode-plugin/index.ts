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

// OpenCode 2.x: default export with an id and an effect (log lines go to OpenCode's own log).
export default {
  id: "opencode-datarobot-skills",
  effect: () =>
    Effect.gen(function* () {
      const configDir = getConfigDir()
      const skillsInstalled = installSkills(configDir)
      installPackages(configDir)
      const themesInstalled = installThemes(configDir)

      if (skillsInstalled > 0 || themesInstalled > 0) {
        yield* Effect.logInfo(
          `Installed ${skillsInstalled} skills${themesInstalled > 0 ? ` and ${themesInstalled} DataRobot theme(s)` : ""}`,
        )
      }
    }),
}
