# Свойства вставки и собственная СП модели: SDK v25

25.11.2026. Offline-проверка официальной справки v25, без CAD/COM/VM,
запуска native workers и изменений установленного SDK. Результаты владельца
CAD ниже — внешние сообщения, здесь нативно не повторялись.

## Вывод

Связь строки с нужным occurrence через Geometry и актуальные Name/Marking
самого occurrence ещё не доказывают актуальность текста СП. Это разные проверки.
Документирован механизм автозаполнения при подключении геометрии и команда
восстановления наследования отдельного свойства в собственной СП. Надёжный
Automation force-resync существующих строк после замены источника пока не принят.

## Update строки и Update описания

| Член v25 | Что установлено |
|---|---|
| [ISpecificationObject.Update](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationobject_update.html) | `BOOL Update()`: применяет изменённые параметры к объекту СП, создаёт объект, если он ещё не создан. Метод унаследован [ISpecificationBaseObject](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationbaseobject.html). Ограничения «только SPW» на этих страницах нет. |
| [ISpecificationDescription](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationdescription.html) | Установка свойств описания доступна для графического документа/модели; в SPW свойства описания read-only. Это ограничение **описания**, не общий запрет Update строки в модели. |
| [ISpecificationDescription.Update](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationdescription_update.html) | `BOOL Update()` применяет параметры описания. Не документирован как перечитывание всех строк из свойств вставок. |
| [ISpecificationTuning.Update](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationtuning_update.html) | Применяет настройки спецификации. Не подмена row.Update и не установленный force-resync. |
| [ISpecificationDescription.NeedRebuild](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationdescription_needrebuild.html) | Управляет обновлением окна при массовых API-изменениях; механизм ускорения, не сертификат актуальности данных и не команда загрузки свойств. |

После `row.Update()==False` изменённый IText в RAM нельзя считать успешно
применённым. Последующий успешный Rebuild не отменяет отказ. Причину False
документация этих методов не раскрывает; утверждения про обязательную SPW,
необходимость визуального Edit или неподдерживаемость modeldesc не доказаны.
[ISpecificationObject.Edit](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationobject_edit.html)
запускает визуальное редактирование; это не обязательный неинтерактивный BeginEdit.

## SyncronizeWithProperties и заполнение

[SyncronizeWithProperties](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationbaseobject_syncronizewithproperties.html)
— BOOL чтения/записи, связанный с обменом данными со свойствами. Установка True
не описана как самостоятельная гарантированная команда refresh. Не путать его с
наследованием каждого свойства от файла-источника.

Документированные точки заполнения:

- [IncludeGeometry(VARIANT PVal, BOOL FillText)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationbaseobject_includegeometry.html):
  FillText=True заполняет наименование, обозначение и массу из свойств объекта
  и включает SyncronizeWithProperties. Метод **добавляет** геометрию; повторная
  передача уже включённого occurrence как идемпотентный refresh не обещана.
- [Geometry setter](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationbaseobject_geometry.html)
  использует текущий Sync и заменяет прежнюю геометрию. Для 3D это может быть
  компонент, тела или позиционные выноски. Переприсвоение только компонента
  способно потерять остальные связи; нельзя предварительно ClearGeometry.
- API5 [D3SpcIncludePart(part, fillTexts)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_d3spcincludepart.html)
  имеет аналогичный fill-механизм. Это работа с объектом СП, а не самостоятельный
  глобальный refresh: контекст точной редактируемой строки нужно установить
  отдельно. Не подставлять произвольный текущий объект.

Для существующей строки, уже точно связанной с нужной геометрией, повторное
подключение/переприсвоение с True остаётся **непринятым отдельным кандидатом**.
Ни сохранение UUID строки, ни отсутствие побочных правок это описание не доказывает.
Прежние [offline-контракты](authoring-boundaries.md) сохраняют наблюдаемый Sync=True
у автоматически созданных строк; они не реализуют native refresh.

## Поддерживаемая семантика «По источнику»

[Справка v25](https://help.ascon.ru/KOMPAS/25/ru-RU/cm_spc_by_source.html) описывает
свойства, переопределённые в сборке: последующие изменения источника к ним не
поступают. Для автоматически сформированной строки связь восстанавливается
командой **По источнику** у ячейки в подчинённом режиме собственной СП модели.
В SPW эта команда недоступна: редактировать нужно связанный документ-источник.
Для ручной строки с подключённым документом предусмотрены другие кнопки —
получение свойств/формата из документа. Отмена По источнику в подчинённом режиме
не предусмотрена; изолированная копия остаётся обязательной границей опыта.

[FAQ v25, случай 2](https://help.ascon.ru/KOMPAS/25/ru-RU/cm_help_sp_faq.html)
уточняет, что ручное изменение обозначения/наименования в собственной СП
отключает получение соответствующего свойства от источника. Это описанное
поведение интерфейса; не доказано, какие флаги успел изменить конкретный
неуспешный API-проход с IText.Str. Проверять их чтением, не выводить из одного False.

## Диагностика перед новым изменением

По свежему exact UUID получить строку, сверить Geometry singleton с нужным
occurrence, затем раздельно снять текст строки и значения свойств occurrence.
[IPropertyKeeper.GetPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_getpropertyvalue.html)
возвращает **Value и FromSource**, BaseUnit — входной признак единиц.
[SetPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_setpropertyvalue.html)
принимает только Property, Value, BaseUnit: аргумента FromSource в setter нет.
Не придумывать reset через четвёртый аргумент, пустой VARIANT или неизвестный command ID.

Для метаданных СЧИ есть [GetObjectPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iproductdatamanager_getobjectpropertyvalue.html)
и [GetObjectLinkPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iproductdatamanager_getobjectlinkpropertyvalue.html),
оба с выходным FromSource; второй требует правильный объект исполнения.
Соответствие property ID/path наименованию и обозначению устанавливать по
актуальным метаданным, не угадывать по номерам колонок или русскому имени.

Снять также [State](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationobject_state.html)
(собственный/из вставки/из вставки, редактированный здесь), Sync, EditSourceObject,
DelegateMode и owner/description. State доступен только для чтения.
[EditSourceObject](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationbaseobject_editsourceobject.html)
связан с передачей правок в документ-владелец;
[DelegateMode](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationdescription_delegatemode.html)
открывает внешние объекты в сборке. Это не переключатели принудительного refresh;
не включать их вслепую ради устранения False.

Если значения properties уже новые, но row text старый, само восстановление
source inheritance может оказаться неприменимым объяснением: отдельно остаётся
путь properties → текст СП. Если FromSource=False, сначала определить, намеренное
ли это переопределение, и только затем выбирать поддерживаемый путь восстановления.
Новая команда массового обновления существующих строк из properties в проверенных
списках SpecificationObject/BaseObject/Description не найдена. Это предел поиска,
не доказательство отсутствия API во всех интерфейсах.

Будущая приёмка: одна строка на новой baseline, UUID и полный Geometry до/после,
явные ожидаемые значения и source flags, отсутствие правок соседей/источников,
BOOL каждого commit; сохранение и независимый fresh RO с той же проверкой.
Текущую partial RAM не переиспользовать для неразличимых повторов.

## Внешнее наблюдение владельца CAD

Прямой API7 old → new теперь принят на сохранённых копиях нескольких assembly
owners; bounds целевых вставок совпали с донорами. В каноническом owner исходные
UUID целевых строк сохранились и Geometry singleton указывал на нужные occurrences
с новыми Name/Marking, но текст СП оставался прежним. После plain IText.Str правки
одной строки row.Update вернул False, Save не выполнялся. Это отдельная граница
приёмки данных СП; успешную синхронизацию или причину отказа здесь не заявляем.
В следующей отдельной fresh-пробе после cleanup установка document.Active=True
не устранила Update=False; текст виден только в RAM, сохранением отказ не обходился.
Этот результат исключает успех именно проверенного кандидата активности,
но не устанавливает общую причину False. Дополнительный SDK native worker не нужен.
