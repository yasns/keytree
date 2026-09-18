import general from './general.json'
import algo from './algo.json'
import hardware from './hardware.json'
import infra from './infra.json'
import l1_menu from './l1_menu.json'
import run_settings from './run_settings.json'

// excluding tcds and external payloads that cannot be verified against JSON schemas
const OVERRIDE: Record<string, object> = {
  algo,
  hardware,
  infra,
  l1_menu,
  run_settings,
}

// definitions hoisted to the root so general's internal "#/definitions/..." refs resolve there
export const schemas = ['general', ...Object.keys(OVERRIDE)].map((cat) => ({
  uri: `inmemory://keytree/${cat}.json`,
  fileMatch: [`**/${cat}.yaml`],
  schema: { definitions: general.definitions, allOf: [general, OVERRIDE[cat] ?? {}] },
}))
