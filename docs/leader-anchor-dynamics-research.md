# Динамика наконечника: SetBaseObject, type12 и пересчёт 2D

23.11.2026. Только чтение квитанций/исходников и официальной справки АСКОН.
CAD/COM/VM не использовались, installed SDK и production recipes не менялись.

## Текущий отрицательный результат: R3–R7

Наличие exact+Valid base и действующего type12 **не гарантирует** следование
наконечника. В исходном внешнем R3 receipt оба конца материального отрезка
сместились одинаково, а tip в исходной параметрической системе не изменился.
В использованном paper-преобразовании tip delta не совпала с material delta.
Проверка остановилась до исправления текста: исправление поля не является
причиной этого наблюдения. Это отрицательное свидетельство для выполненного
порядка вызовов, не доказательство невозможности всех native механизмов.

**Кандидат с дополнительным документным пересчётом теперь испытан и не
обеспечил следование.** Прежняя рекомендация считать его первым следующим
экспериментом заменена результатами R4/R5. Перечитаны внешний итоговый отчёт
`DYNAMIC_CHECK_LIMITATION_R7.md`, raw R4–R7 и тексты R4/R5/R6; они не исполнялись.
В публичный SDK реальные UUID, файлы изделия и его геометрия не перенесены.

| Внешний опыт | Сохранённое наблюдение | Граница вывода |
|---|---|---|
| R3: av.Rebuild | True; rigid material displacement, но другая tip delta; base/type12 Valid | FAIL следования до text repair |
| R4: IKompasDocument2D1.CompleteRebuildDocument | True на M0/M1/обратной M0; follows=False, returned=True | FAIL следования; recorded return не является успешным циклом движения/Save/RO |
| R5: IKompasDocument2D1.RebuildDocument и PumpWaitingMessages | True; все 16 отсчётов follows=False | FAIL следования; дополнительное ожидание в этом опыте не помогло |
| R6: дополнительный type2 PointOnCurve | Единственная branch point совпала с tip; Create=False, Valid=False; raw phase=starting, Save_invocations=0 | Неудача создания **до** M1, не четвёртый опыт движения; финальный restored PASS отсутствует |
| R7: getter-only inventory | В том же процессе коллекция стала пустой вместо прежних девяти документов | Причина не установлена; не объявлять crash/restart/штатное закрытие/сохранение |

Прежний размерный сценарий `scripts/validate_associative_drawing.py` действительно
вызывает RebuildDocument после перестроения видов. Его успех не переносится
на positional leader, для которого дополнительные варианты теперь отрицательны.
Нельзя рекомендовать повторить тот же документный rebuild только потому, что
его BOOL True. Результаты относятся к проверенной выноске и recipes; ни причина,
ни универсальная невозможность native association этим не доказаны.

Raw R6 оборвался на терминальном guard и не содержит итоговой проверки cleanup/
сохранности. Восстановление из R4/R5 не переносится на состояние после R6.
Позже владелец CAD отдельно сообщил о проверке полных файловых SHA и восстановлении
приложения после snapshot. Это отдельное owner-reported восстановление, не
ретроактивный R6 restored PASS и не независимая проверка файлов этим SDK-проходом.

## После передачи ресурса: synthetic unique-source-revision тоже отрицателен

После явного handover выполнен отдельный опыт на полностью новой synthetic
plate/assembly/leader, без файлов изделия. Same-filename и unique-source-revision
дали одинаковое отставание tip при реальном material displacement, сохранённое
после двух RO cycles. Native sheet coordinates независимо проверены режимами
-7/-2. Unique revision больше не непроверенный следующий кандидат **для этого
fixture/рецепта**; его нельзя снова рекомендовать только из-за успеха размерного
сценария. Полный отрицательный результат, ограничения возврата/recentering,
visual exports и независимые guards — в [native отчёте](native-leader-source-revisions.md).
Пять оставленных RO документов и protected file SHA сохранены, synthetic docs
закрыты, ресурс освобождён. Новых native jobs или попыток возобновить R6 нет.

Структурная связь, финальный текст/геометрия текущей выдачи и динамика будущих
изменений оцениваются отдельно. Этот SDK-контекст не принимает решения о выпуске
инженерного комплекта. Полноценное автоматическое следование остаётся непринятым.

## Что документирует SDK

| API | Документировано | Что из этого не следует |
|---|---|---|
| [ksConstraintTypeEnum](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksconstrainttypeenum.html) | type12 = ksCAssociation; type2 — точка на кривой; type11 — совпадение точек | type12 сам по себе не определяет точку/параметр вдоль контура |
| [SetBaseObject](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ibranchs_setbaseobject.html) | BOOL, branch Index, IDrawingObject, SegmentIndex | Значение -1 для простой линии и его отличие от point-anchor не раскрыты |
| [Constraint.Index](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_index.html) | Индекс точки на текущем объекте, обычно с 0 | Не определяет соответствие точек IPositionLeader; -1 не расшифрован |
| [Constraint.SegmentIndex](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_segmentindex.html) и [PartnerSegmentIndex](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint_partnersegmentindex.html) | Сегмент текущего объекта и партнёра — разные свойства | Setter SegmentIndex=-1 нельзя приравнивать к getter constraint.SegmentIndex=0: разные контексты |
| [IAssociationView.Rebuild](https://help.ascon.ru/KOMPAS_SDK/24/ru-RU/iassociationview_rebuild.html) | BOOL Rebuild(), перестроение вида | Нет обещания полного пересчёта всех 2D-ограничений/аннотаций документа |
| [IKompasDocument2D1.RebuildDocument](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument2d1_rebuilddocument.html) | BOOL RebuildDocument(), перестроение 2D-документа | В R5 проверен: не обеспечил следование данной выноски |
| [IDrawingDocument.RebuildViews](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/idrawingdocument_rebuildviews.html) | BOOL RebuildViews(VARIANT Views), список видов, с v24 | Не указаны формат SAFEARRAY и значение empty для «всех»; wrapper сверить по installed v25 вне этой offline-задачи |
| [CheckAssociation](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument2d1_checkassociation.html) | Проверка/восстановление, аргумент DimensionTypes — типы размеров, результат enum плюс counts | Это не подтверждённый универсальный Solve для positional leaders; возможна модификация связей |

Гипотеза «-1 связывает объект, но не material point» согласуется с наблюдением,
но официальным описанием не подтверждена. Документный rebuild и ожидание уже
не дали результата в R4/R5; это не устанавливает точную причину. Угадывание raw
enum/indices не заменяет независимого доказательства point attachment.

Руководство v25 прямо относит позиционные обозначения/линии-выноски к
[ассоциативным объектам](https://help.ascon.ru/KOMPAS/25/ru-RU/2015_210_3_2_assoc_ob.html).
Поэтому наличие type12 у такой выноски само по себе нормально. В
[особенностях обозначений](https://help.ascon.ru/KOMPAS/25/ru-RU/1818_7_2_4_osob_rab_assoc_obozn.html)
указано, что ассоциативными могут быть отдельные ответвления, а параметрический
режим выбирается до их создания. Линейный размер там выделен как особый случай
со связями точек вместо ограничения «Ассоциативность». Следовательно, прежний
успех размерного примера с type11 нельзя механически переносить на leader.
Если когда-либо отдельно согласуется GUI-контроль, он должен включать выноску
на проекции с повторным
выбором base в режиме редактирования. Дополнительный простой 2D line/leader
контроль поможет отделить обычную 2D association от обновления 3D-проекции.

В [IParametriticConstraint](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/iparametriticconstraint.html)
свойства существующего ограничения не предлагается редактировать напрямую:
для другого набора параметров нужен новый constraint. Не удалять все constraints
или старый type12 для эксперимента в production. API5 не предоставляет создание/
чтение типа «Ассоциативная связь», поэтому обход через API5 не заменяет этот gate.
Автоматический Associate тоже не даёт доказанной точной точки нужного owner.

Для такого будущего GUI-контроля создать именно endpoint/material-point attachment
минимальной
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
