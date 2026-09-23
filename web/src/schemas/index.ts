import shepherd from './shepherd.json'

export const schemas = [
  {
    uri: 'inmemory://keytree/shepherd.json',
    fileMatch: ['**/*.yaml'],
    schema: shepherd,
  },
]
