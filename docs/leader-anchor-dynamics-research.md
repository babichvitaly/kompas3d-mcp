# Динамика наконечника: SetBaseObject, type12 и пересчёт 2D

23.11.2026. Только чтение квитанций/исходников и официальной справки АСКОН.
CAD/COM/VM не использовались, installed SDK и production recipes не менялись.

## Вывод и следующий native эксперимент

Наличие exact+Valid base и действующего type12 **не гарантирует** следование
наконечника. В новом внешнем native receipt оба конца материального отрезка
сместились одинаково, а tip в исходной параметрической системе не изменился.
В использованном paper-преобразовании tip delta не совпала с material delta.
Проверка остановилась до исправления текста: исправление поля не является
причиной этого наблюдения. Это отрицательное свидетельство для выполненного
порядка вызовов, не доказательство невозможности всех native механизмов.

**Первый кандидат для сравнения — IKompasDocument2D1.RebuildDocument() после
перестроения видов.** В исследованном пилоте выполнялся av.Rebuild(), этого
документного шага до измерения не было. Он уже присутствует в прежнем
синтетическом SDK-сценарии для ассоциативного размера:
`scripts/validate_associative_drawing.py`, функции `_rebind_views` и `main`.
`skills/kompas-api/references/parametrics-documents.md` описывает ту же
последовательность. Успех размерного сценария не подтверждает позиционную выноску.

Следующий experiment-first порядок на независимых disposable baselines:

| Вариант | Порядок | Что разделяет |
|---|---|---|
| A | source placement/save -> av.Rebuild -> немедленное чтение | Контроль исходного отрицательного наблюдения |
| B | тот же source stimulus -> av.Rebuild -> cast drawing в IKompasDocument2D1 -> RebuildDocument -> чтение | Нужен ли дополнительный документный пересчёт |
| C | тот же stimulus -> IDrawingDocument.RebuildViews(explicit affected views) -> RebuildDocument -> чтение | Влияет ли перестроение группы зависимых видов |
| D | тот же минимальный документ с привязкой, созданной штатной GUI-командой | Какая native point/segment связь реально обеспечивает tip following |

Каждый вариант — новая копия; не продолжать B/C поверх изменённого результата A
и не добавлять retry. Иначе причинность теряется. RebuildDocument/RebuildViews
тоже могут менять текст/геометрию: до любого text repair снять полную геометрию,
typed fields, native row lookup и poses/printability. BOOL True не заменяет
геометрическую проверку. Нативный ресурс этим исследованием не запрашивался.

## Что документирует SDK

| API | Документировано | Что из этого не следует |
|---|---|---|
| [ksConstraintTypeEnum](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksconstrainttypeenum.html) | type12 = ksCAssociation; type2 — точка на кривой; type11 — совпадение точек | type12 сам по себе не определяет точку/параметр вдоль контура |
| [SetBaseObject](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ibranchs_setbaseobject.html) | BOOL, branch Index, IDrawingObject, SegmentIndex | Значение -1 для простой линии и его отличие от point-anchor не раскрыты |
| [Constraint.Index](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_index.html) | Индекс точки на текущем объекте, обычно с 0 | Не определяет соответствие точек IPositionLeader; -1 не расшифрован |
| [Constraint.SegmentIndex](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_segmentindex.html) и [PartnerSegmentIndex](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_partnersegmentindex.html) | Сегмент текущего объекта и партнёра — разные свойства | Setter SegmentIndex=-1 нельзя приравнивать к getter constraint.SegmentIndex=0: разные контексты |
| [IAssociationView.Rebuild](https://help.ascon.ru/KOMPAS_SDK/24/ru-RU/iassociationview_rebuild.html) | BOOL Rebuild(), перестроение вида | Нет обещания полного пересчёта всех 2D-ограничений/аннотаций документа |
| [IKompasDocument2D1.RebuildDocument](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument2d1_rebuilddocument.html) | BOOL RebuildDocument(), перестроение 2D-документа | Не гарантирует исправление данного positional leader; требует испытания |
| [IDrawingDocument.RebuildViews](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/idrawingdocument_rebuildviews.html) | BOOL RebuildViews(VARIANT Views), список видов, с v24 | Не указаны формат SAFEARRAY и значение empty для «всех»; wrapper сверить по installed v25 вне этой offline-задачи |
| [CheckAssociation](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument2d1_checkassociation.html) | Проверка/восстановление, аргумент DimensionTypes — типы размеров, результат enum плюс counts | Это не подтверждённый универсальный Solve для positional leaders; возможна модификация связей |

Гипотеза «-1 связывает объект, но не material point» согласуется с наблюдением,
но официальным описанием не подтверждена. Также не исключён неполный цикл
пересчёта. Разделить их позволяют B и D, а не изменение raw enum наугад.

Руководство v25 прямо относит позиционные обозначения/линии-выноски к
[ассоциативным объектам](https://help.ascon.ru/KOMPAS/25/ru-RU/2015_210_3_2_assoc_ob.html).
Поэтому наличие type12 у такой выноски само по себе нормально. В
[особенностях обозначений](https://help.ascon.ru/KOMPAS/25/ru-RU/1818_7_2_4_osob_rab_assoc_obozn.html)
указано, что ассоциативными могут быть отдельные ответвления, а параметрический
режим выбирается до их создания. Линейный размер там выделен как особый случай
со связями точек вместо ограничения «Ассоциативность». Следовательно, прежний
успех размерного примера с type11 нельзя механически переносить на leader.
GUI-контроль D должен включать существующую выноску на проекции с повторным
выбором base в режиме редактирования. Дополнительный простой 2D line/leader
контроль поможет отделить обычную 2D association от обновления 3D-проекции.

В [IParametriticConstraint](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint.html)
свойства существующего ограничения не предлагается редактировать напрямую:
для другого набора параметров нужен новый constraint. Не удалять все constraints
или старый type12 для эксперимента в production. API5 не предоставляет создание/
чтение типа «Ассоциативная связь», поэтому обход через API5 не заменяет этот gate.
Автоматический Associate тоже не даёт доказанной точной точки нужного owner.

Для D вручную создать именно endpoint/material-point attachment минимальной
выноски и прочитать branch base, все native constraint indices/segments/partners.
Потом проверить source displacement. Только после этого задавать Index и
PartnerIndex через NewConstraint/Create на другой копии. Угадывать, что 0 — tip,
нельзя; type2 оставляет степень свободы вдоль линии и не фиксирует material point.
Случай type11 также требует экспериментально установленного point mapping.

## Координаты: исправлен offline-контракт

[ksDrawingObjectParamTypeEnum](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksdrawingobjectparamtypeenum.html)
документирует **-1 ksAllParam, -2 ksSheetAllParam, -7 ksViewAllParam**.
Предыдущий DTO использовал NonnegativeInt и ошибочно отвергал реальные значения.
Теперь leader/root-projection DTO используют strict signed enum; fixtures
исправлены и добавлены positive/negative regressions.

[DrawingObjectParamType](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/idrawingobject_drawingobjectparamtype.html)
определяет матрицу пересчёта координат/углов/скаляров. Название ksAllParam само
по себе не обещает «немасштабированные координаты вида». На disposable pilot
нужно независимо подтвердить paper coordinates через документированный sheet
режим -2 и согласовать их с -7/измеренной affine map. Не использовать Current
ради конвертации. Сохранить и сверить getter modes до/после такого чтения.
Изменение X/Y вида после Rebuild учитывать, не требовать прежнюю origin без
доказательства, что это нужный invariant динамического испытания.

## UUID: первый regex match не является native identity

Rebuild добавил первую typed position-строку с новым presentation key, при этом
старый canonical key сохранился во второй строке и прямой native row lookup
продолжил возвращать canonical row. Выводить identity из первого key в Str
ошибочно. Это не разрешение принять изменившийся двухстрочный текст на выпуск.

Новый getter-only `canonical_position_identity` проверяет direct singleton
RowLookup и typed IText/ITextLine/ITextItem property fields по canonical key
независимо от порядка. Дополнительные поля отдельно отмечаются. Функция ничего
не удаляет, не пишет Positions.Str и не ослабляет exact-text oracle копирования.
Identity, final text formatting и geometric following остаются тремя gate.

## Новая синтетическая диагностика движения

`assess_projected_tip_translation` принимает baseline/moved tip, два конца
материального отрезка и независимо измеренные affine maps в paper coordinates.
Поддерживает неизменную линейную basis и измеренную трансляцию/recentering вида.
Проверяет исходное попадание tip на конечный отрезок, rigid translation обоих
endpoints (включая reversed enumeration), действительное ненулевое material
displacement и равенство **обоих** компонентов tip/material delta. Скользящий
tip на той же прямой не проходит. Base/type12 читаются только как диагностика.

Неизменившаяся material projection, неправильная identity, scale/rotation change
или деформация — `inconclusive` для этого узкого translation oracle; корректный
stimulus с отставшим tip — `motion_does_not_follow`. Удачное совпадение даёт только
`motion_follows_in_reported_evidence`, а не native dynamics acceptance. Для неё
ещё нужны запрет ручного движения tip во время stimulus, Save/reopen в изменённом
состоянии, полный placement/Fixed restore, повторный Save/reopen и visual checks.

Полные raw receipts остаются вне публичного SDK. В fixture нет реальных UUID,
путей изделий, размеров/placement или измеренных product deltas.
