import type { Plugin } from "@opencode-ai/plugin"
import { cpSync, existsSync, mkdirSync, readdirSync } from "fs"
import { homedir } from "os"
import { dirname, join, resolve } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const BUNDLED_SKILLS = resolve(__dirname, "..", "skills")
const BUNDLED_THEME = resolve(__dirname, "themes", "datarobot.json")

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

function installTheme(configDir: string): boolean {
  if (!existsSync(BUNDLED_THEME)) {
    return false
  }
  const themesDir = join(configDir, "opencode", "themes")
  const target = join(themesDir, "datarobot.json")
  mkdirSync(themesDir, { recursive: true })
  cpSync(BUNDLED_THEME, target)
  return true
}

export const DataRobotSkillsPlugin: Plugin = async ({ client }) => {
  const configDir = getConfigDir()
  const skillsInstalled = installSkills(configDir)
  const themeInstalled = installTheme(configDir)

  if (skillsInstalled > 0 || themeInstalled) {
    await client.app.log({
      body: {
        service: "opencode-datarobot-skills",
        level: "info",
        message: `Installed ${skillsInstalled} skills${themeInstalled ? " and DataRobot theme" : ""}`,
      },
    })
  }

  return {}
}

