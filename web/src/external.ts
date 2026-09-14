import { useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'

// placeholder until the owning external DBs are defined
const EXTERNAL_OPTIONS: Record<string, string[]> = {
  'cms_run/clock_source': ['LHC', 'LOCAL'],
  'l1_hlt/hlt_key': [
    '/cdaq/circulating/2022/v1.0/HLT/V1',
    '/cdaq/circulating/2022/v1.0/HLT/V2',
    '/cdaq/circulating/2022/v1.1/HLT/V1',
    '/cdaq/circulating/2022/v2.0/HLT/V1',
    '/cdaq/circulating/2022/v3.0/HLT/V1',
    '/cdaq/circulating/2022/v3.1/HLT/V1',
    '/cdaq/circulating/2022/v3.1/NoGPU/HLT/V1',
    '/cdaq/circulating/2022/v3.1/NoGPU/HLT/V2',
    '/cdaq/circulating/2022/v3.1/NoGPU/HLT/V3',
    '/cdaq/circulating/2022/v3.2/HLT/V1',
    '/cdaq/circulating/2022/v3.2/HLT/V2',
    '/cdaq/circulating/2022/v3.2/HLT/V3',
    '/cdaq/circulating/2022/v3.2/HLT/V4',
    '/cdaq/circulating/2022/v3.2/HLT/V5',
    '/cdaq/circulating/2022/v3.2/HLT/V6',
    '/cdaq/circulating/2022/v3.3/HLT/V1',
    '/cdaq/circulating/2022/v3.3/HLT/V2',
    '/cdaq/circulating/2022/v3.3/HLT/V3',
    '/cdaq/circulating/2022/v3.3/HLT/V4',
    '/cdaq/circulating/2022/v3.3/HLT/V5',
    '/cdaq/circulating/2022/v3.3/HLT/V6',
    '/cdaq/circulating/2022/v3.3/HLT/V7',
    '/cdaq/circulating/2022/v3.3/HLT/V8',
    '/cdaq/circulating/2022/v3.4/HLT/V1',
    '/cdaq/circulating/2022/v3.4/HLT/V2',
    '/cdaq/circulating/2022/v3.4/HLT/V3',
    '/cdaq/circulating/2022/v4.0/HLT/V1',
    '/cdaq/circulating/2022/v4.0/HLT/V10',
    '/cdaq/circulating/2022/v4.0/HLT/V2',
    '/cdaq/circulating/2022/v4.0/HLT/V3',
    '/cdaq/circulating/2022/v4.0/HLT/V4',
    '/cdaq/circulating/2022/v4.0/HLT/V5',
    '/cdaq/circulating/2022/v4.0/HLT/V6',
    '/cdaq/circulating/2022/v4.0/HLT/V7',
    '/cdaq/circulating/2022/v4.0/HLT/V8',
    '/cdaq/circulating/2022/v4.0/HLT/V9',
    '/cdaq/circulating/2022/v4.1/HLT/V1',
    '/cdaq/circulating/2022/v4.2/HLT/V1',
    '/cdaq/circulating/2022/v4.3/HLT/V1',
    '/cdaq/circulating/2022/v4.3/HLT/V2',
    '/cdaq/circulating/2022/v4.3/HLT/V3',
    '/cdaq/circulating/2022/v4.3/HLT/V4',
    '/cdaq/circulating/2022/v4.3/HLT/V5',
    '/cdaq/circulating/2022/v4.3/HLT/V6',
    '/cdaq/circulating/2022/v4.4/HLT/V1',
    '/cdaq/circulating/2022/v4.4/HLT/V2',
    '/cdaq/circulating/2022/v4.5/HLT/V1',
    '/cdaq/circulating/2022/v4.5/HLT/V2',
    '/cdaq/circulating/2023/v1.0/HLT/V1',
    '/cdaq/circulating/2023/v1.1/HLT/V1',
  ],
  'l1_hlt/hlt_sw_arch': [
    'CMSSW_16_1_1_patch3 el8_amd64_gcc13',
    'CMSSW_16_1_1_patch1 el8_amd64_gcc13',
    'CMSSW_16_1_1 el8_amd64_gcc13',
    'CMSSW_16_0_7_patch1 el8_amd64_gcc13',
    'CMSSW_16_0_7 el8_amd64_gcc13',
    'CMSSW_16_0_6_patch1 el8_amd64_gcc13',
    'CMSSW_16_0_6 el8_amd64_gcc13',
    'CMSSW_16_0_4_patch1 el8_amd64_gcc13',
    'CMSSW_16_0_4 el8_amd64_gcc13',
    'CMSSW_16_0_3 el8_amd64_gcc13',
    'CMSSW_16_0_2_patch1 el8_amd64_gcc13',
    'CMSSW_16_0_2 el8_amd64_gcc13',
    'CMSSW_15_1_0_patch3 el8_amd64_gcc12',
  ],
  'cms_run/tracker_run_key': ['COSMICS', 'DEFAULT', 'VR', 'ZS'],
  'cms_run/es_run_key': [
    ':HighGain-TCDS',
    ':LowGain-TCDS',
    'GR_Phys:HighGain',
    'GR_Phys:HighGain-TCDS',
    'GR_Phys:LowGain',
    'GR_Phys:LowGain-TCDS',
    'HighGainTCDS',
  ],
  'cms_run/ecal_run_key': [
    ':Beam-SR-HighLaser',
    ':DelayScan-SR',
    ':FullReadout',
    ':SelectiveReadout',
    ':SelectiveReadout-NoLaser',
    ':SelectiveReadout_test',
    ':TCC_Patterns',
    ':TCC_Patterns_LTC',
    ':TPGPatternGenerator',
    ':ZeroSuppression',
    ':ZeroSuppression-NoLaser',
    'Beam-NoTrigger',
    'Cosmics-SR',
    'Cosmics-SR-NoLaser',
  ],
  'cms_run/hcal_run_key': ['ZS', 'noZS', 'test-ZS'],
  'cms_run/hf_run_key': ['ZS', 'noZS', 'test-ZS'],
  'cms_run/daq_run_key': ['TIER0_TRANSFER_OFF', 'TIER0_TRANSFER_ON', 'TIER0_TRANSFER_ON_NOPARKING'],
  'cms_run/dqm_run_key': [
    'cosmic_run',
    'cosmic_run_stage1',
    'hi_run',
    'hpu_run',
    'pp_run',
    'pp_run_stage1',
  ],
  'cms_run/trg_run_key': ['Automatic', 'ExpertMode'],
  'cms_run/tcds_run_key': ['BxInfoFromDip', 'NoBxInfoFromDip'],
  'cms_run/use_primary_tcds': ['true', 'false'],
}
const EXTERNAL_FALLBACK = ['dummy']

function externalOptions(key: string): string[] {
  return EXTERNAL_OPTIONS[key] ?? EXTERNAL_FALLBACK
}

async function fetchL1HltModes(): Promise<string[]> {
  const changes = useChangesStore()
  return useNavStore()
    .fetchModesByPath('l1_hlt', 'conf')
    .then((modes) => modes.filter((m) => !changes.archived(m)).map((m) => m.name))
}

// Subsystem+node keys whose option list must be fetched rather than read from EXTERNAL_OPTIONS
const DYNAMIC_EXTERNAL_OPTIONS: Record<string, () => Promise<string[]>> = {
  'cms_run/l1_hlt_mode': fetchL1HltModes,
}

export function resolveExternalOptions(subsystem: string, nodeName: string): Promise<string[]> {
  const key = `${subsystem}/${nodeName}`
  return (DYNAMIC_EXTERNAL_OPTIONS[key] ?? (() => Promise.resolve(externalOptions(key))))()
}
