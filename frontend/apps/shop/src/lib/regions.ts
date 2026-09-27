/** Regions of Uzbekistan, in the order people expect (capital first). Values are i18n keys. */
export const REGIONS = [
  'toshkent_sh',
  'toshkent',
  'andijon',
  'buxoro',
  'fargona',
  'jizzax',
  'xorazm',
  'namangan',
  'navoiy',
  'qashqadaryo',
  'qoraqalpogiston',
  'samarqand',
  'sirdaryo',
  'surxondaryo',
] as const

export type RegionKey = (typeof REGIONS)[number]
