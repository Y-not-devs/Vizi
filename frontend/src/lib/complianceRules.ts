/**
 * Нормативная база кассовой дисциплины банков второго уровня Республики Казахстан
 * Источник: Постановление Правления Национального Банка Республики Казахстан 
 * от 29 ноября 2019 года № 231 (adilet.zan.kz)
 */

export interface RuleDetail {
  document: string
  clause: string
  fullCitation: string
  summary: string
  legalRequirement: string
}

export const NORMATIVE_DATABASE: Record<string, RuleDetail> = {
  phone: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 12',
    fullCitation: 'Пункт 12 Правил № 231 НБ РК',
    summary: 'Запрет нахождения личных средств связи на кассовом узле',
    legalRequirement: 'Кассиру запрещается хранить на рабочем месте и использовать личные мобильные телефоны, смартфоны, фото- и видеоаппаратуру, а также личные наличные деньги во время совершения кассовых операций.'
  },
  unauthorized_access: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 14',
    fullCitation: 'Пункт 14 Правил № 231 НБ РК',
    summary: 'Несанкционированный доступ посторонних лиц в кассовую зону',
    legalRequirement: 'Доступ в помещение кассы и к рабочему месту кассира лицам, не имеющим права на проведение кассовых операций или контроль, категорически воспрещен.'
  },
  cashier_absent: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 22',
    fullCitation: 'Пункт 22 Правил № 231 НБ РК',
    summary: 'Оставление кассового узла и ценностей без присмотра',
    legalRequirement: 'При временном оставлении рабочего места кассир обязан убрать все наличные деньги и ценности в сейф/тумбу и закрыть их на ключ. Нахождение открытого лотка или денег без кассира запрещено.'
  },
  counting: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 20',
    fullCitation: 'Пункт 20 Правил № 231 НБ РК',
    summary: 'Пересчет наличных вне визуального контроля клиента',
    legalRequirement: 'Прием и выдача наличных денег осуществляются полистным и поштучным пересчетом под непосредственным и непрерывным наблюдением клиента.'
  },
  id_check: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 18',
    fullCitation: 'Пункт 18 Правил № 231 НБ РК',
    summary: 'Нарушение регламента идентификации клиента',
    legalRequirement: 'Кассир обязан удостовериться в личности клиента путем сличения фотографии в документе, удостоверяющем личность (ID-карта, паспорт), с лицом клиента перед проведением расходной или приходной операции.'
  },
  theft_cash: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 25',
    fullCitation: 'Пункт 25 Правил № 231 НБ РК',
    summary: 'Неправомерные манипуляции с банкнотами и сокрытие ценностей',
    legalRequirement: 'Все перемещения наличных денег должны производиться открыто в пределах зоны лотка и счетно-сортировальных машин. Сокрытие банкнот в карманах, под прилавком или вне зоны видимости камер запрещено.'
  },
  fake_receipt: {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Пункт 27',
    fullCitation: 'Пункт 27 Правил № 231 НБ РК',
    summary: 'Подмена денежных билетов либо нарушение порядка оформления документов',
    legalRequirement: 'Запрещается имитация вложения денежных знаков, подмена пачек наличных денег посторонними предметами, черновиками или незаверенными бланками.'
  }
}

/**
 * Определение нормативной ссылки по типу нарушения
 */
export function resolveRuleInfo(type: string, existingRule?: string): RuleDetail {
  if (existingRule && existingRule.trim().length > 0) {
    return {
      document: 'Правила № 231 НБ РК',
      clause: existingRule,
      fullCitation: existingRule,
      summary: type,
      legalRequirement: `Требование кассовой дисциплины согласно: ${existingRule}`
    }
  }

  const lower = (type || '').toLowerCase()

  if (lower.includes('телефон') || lower.includes('смартфон') || lower.includes('phone') || lower.includes('предмет')) {
    return NORMATIVE_DATABASE.phone
  }
  if (lower.includes('посторонн') || lower.includes('доступ') || lower.includes('access')) {
    return NORMATIVE_DATABASE.unauthorized_access
  }
  if (lower.includes('отсутств') || lower.includes('absent') || lower.includes('оставлен')) {
    return NORMATIVE_DATABASE.cashier_absent
  }
  if (lower.includes('пересчет') || lower.includes('count') || lower.includes('клиент')) {
    return NORMATIVE_DATABASE.counting
  }
  if (lower.includes('удостоверен') || lower.includes('паспорт') || lower.includes('id') || lower.includes('идентификац')) {
    return NORMATIVE_DATABASE.id_check
  }
  if (lower.includes('краж') || lower.includes('сокрыт') || lower.includes('theft') || lower.includes('манипуляц')) {
    return NORMATIVE_DATABASE.theft_cash
  }
  if (lower.includes('подмен') || lower.includes('чек') || lower.includes('fake') || lower.includes('квитанц')) {
    return NORMATIVE_DATABASE.fake_receipt
  }

  return {
    document: 'Правила ведения кассовых операций в банках второго уровня РК (Постановление № 231 НБ РК)',
    clause: 'Раздел 2, Общие требования кассовой дисциплины',
    fullCitation: 'Постановление Правления НБ РК № 231',
    summary: type || 'Требование регламента кассового обслуживания',
    legalRequirement: 'Соблюдение установленного порядка совершения кассовых операций в кассах банков второго уровня.'
  }
}
