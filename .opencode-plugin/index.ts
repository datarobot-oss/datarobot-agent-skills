import type { Plugin } from "@opencode-ai/plugin"
import { cpSync, existsSync, mkdirSync, readdirSync } from "fs"
import { homedir } from "os"
import { dirname, join, resolve } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const BUNDLED_SKILLS = resolve(__dirname, "..", "skills")
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

function installThemes(configDir: string): number {
  const themesDir = join(configDir, "opencode", "themes")
  mkdirSync(themesDir, { recursive: true })

  const themes = readdirSync(BUNDLED_THEMES_DIR).filter((f) => f.endsWith(".json"))
  for (const theme of themes) {
    cpSync(join(BUNDLED_THEMES_DIR, theme), join(themesDir, theme))
  }
  return themes.length
}

export const DataRobotSkillsPlugin: Plugin = async ({ client }) => {
  const configDir = getConfigDir()
  const skillsInstalled = installSkills(configDir)
  const themesInstalled = installThemes(configDir)

  if (skillsInstalled > 0 || themesInstalled > 0) {
    await client.app.log({
      body: {
        service: "opencode-datarobot-skills",
        level: "info",
        message: `Installed ${skillsInstalled} skills${themesInstalled > 0 ? ` and ${themesInstalled} DataRobot theme(s)` : ""}`,
      },
    })
  }

  return {}
}

