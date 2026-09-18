import { describe, expect, it } from 'vitest'
import Ajv from 'ajv'
import { parse } from 'yaml'
import general from './general.json'
import validYaml from './fixtures/valid.yaml?raw'
import invalidYaml from './fixtures/invalid.yaml?raw'

const ajv = new Ajv({ allErrors: true, allowUnionTypes: true })
const validate = ajv.compile(general)

describe('general.json', () => {
  it('accepts a real two-crate config', () => {
    const valid = validate(parse(validYaml))
    expect(validate.errors).toBeNull()
    expect(valid).toBe(true)
  })

  it('rejects a bad slot type and an unknown top-level key', () => {
    const valid = validate(parse(invalidYaml))
    expect(valid).toBe(false)
    const paths = validate.errors?.map((e) => e.instancePath + ' ' + e.schemaPath).join('\n')
    expect(paths).toContain('/system/boards/serenity127/slot')
    expect(paths).toMatch(/additionalProperties/)
  })

  it('accepts a §-prefixed key with an explicit :param suffix and a direct value', () => {
    const valid = validate({
      contexts: {
        'serenity.processors': {
          parameters: { '§configureFireflyRx,configureFireflyTx:ids': 'auto' },
        },
      },
    })
    expect(validate.errors).toBeNull()
    expect(valid).toBe(true)
  })

  it('still accepts a bare §-prefixed key mapping to a param object', () => {
    const valid = validate({
      contexts: {
        'serenity.processors': {
          parameters: { '§configureRxBuffers': { ids: [], mode: [] } },
        },
      },
    })
    expect(validate.errors).toBeNull()
    expect(valid).toBe(true)
  })
})
