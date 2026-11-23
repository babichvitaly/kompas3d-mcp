# Привязка существующих позиционных выносок: offline-контракт

Дата: 23.11.2026. Общие модули: `leader_anchors.py`, `native_returns.py`.
Здесь нет подключения к CAD, управления VM, установленного native adapter,
новой MCP-команды или изменения существующих инструментов. Испытания используют
только синтетические DTO и подставные объекты. Инженерные данные не переносились.

## Основание и границы наблюдений

Разобраны исходные квитанции пилота, независимое чтение после открытия,
узкий context-пилот, отказ root-query и старый обход через вставленные children.
Они остаются вне публичного репозитория; исходные квитанции не переписывались.

| Наблюдение | Что можно утверждать |
|---|---|
| В v25 setter с `SegmentIndex=-1` и собственный Update вернули True; getter показал exact+Valid base | Узкий рецепт для отрезков/окружностей; поддержка других типов/версий не установлена |
| Пилот помечен failed на `assert Save()`; независимый RO receipt содержит две связи с Valid base и type12 | Ошибка assert не доказывает отказ сохранения; независимое сохранённое состояние — отдельное доказательство |
| Числовые refs двух сохранённых проекций изменились при открытии | Сравнивать base с заново полученной геометрией текущего цикла, а не с историческим числом |
| Root-query завершился RPC_E_SERVERFAULT; проверенный обход запрашивает вставленные children | Новый helper вообще не запрашивает special root; одиночная корневая деталь без вставок остаётся неподдержанной |
| Exact+Valid base и type12 Valid при пустом Partner в presentation | Пустой Partner допускается как структурное наблюдение; динамика из этого не следует |
| В одном context-пилоте Current=True показал Scale=0; восстановление Update не прошло | Основание сохранять/сверять состояние и избегать setter в этом рецепте; общего бага Current не заявляем |

Официальные Automation-контракты: [Save(void)](https://help.ascon.ru/KOMPAS_SDK/24/ru-RU/ikompasdocument_save.html),
[IDrawingObject.Update(BOOL)](https://help.ascon.ru/KOMPAS_SDK/24/ru-RU/idrawingobject_update.html),
[IParametriticConstraint.Create(BOOL)](https://help.ascon.ru/KOMPAS_SDK/24/ru-RU/iparametriticconstraint_create.html),
[IBranchs.SetBaseObject(BOOL)](https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/ibranchs_setbaseobject.html).
Справка setter не объясняет специальное значение -1 для простой линии.
Это эмпирический рецепт v25, а не обещание SDK для всех примитивов.

## Контракт исполнения

`bind_existing_leader_owned(plan, adapter)` работает с уже существующей
выноской и ответвлением. Документ заранее активирован владельцем сеанса.
Helper не устанавливает Current/Active, не двигает наконечник или полку,
не создаёт constraints, не меняет UUID/typed field, не сохраняет/закрывает/перестраивает.
Он выполняет только один SetBaseObject с -1 и собственный Update выноски.

1. Проверить полный protected baseline и semantic owner **до nearest curve**.
   Для canonical-view нужен UUID -> exact singleton row.Geometry occurrence;
   его свежий reference должен совпасть с target reference.
   Для presentation обязательны точный путь вставки, полный путь и SHA файла,
   placement, owner subtree SHA, доказанная принадлежность canonical subtree,
   отдельная семантическая идентичность экземпляра и pinned mapping digest.
   Сравнение basename и выбор одного из повторных экземпляров по SHA запрещены.
2. Пройти только разрешённое поддерево. Special MainTopPart не передавать в
   AssociationObjects даже при отсутствии children. Каждый вставленный узел
   запрашивается один раз; refs геометрии дедуплицируются в пределах операции.
   Есть пределы узлов, глубины и **сырых** entries, включая дубли. Переполнение,
   конфликт путей/refs, неверный child и пустой результат прекращают выбор.
3. Снять detached snapshot каждой уникальной поддержанной кривой один раз.
   Допустимы только line/circle, Valid, не Temp, видимые, curve+geometry,
   в точном owning view и с тем же DrawingObjectParamType, что у выноски.
   Координаты near_point и geometry должны быть в этой же системе; native
   collector обязан получить mode и координаты, не подставлять их вручную.
   Выбрать nearest в явном расстоянии; равнозначные кандидаты и центр окружности
   без уникального ближайшего направления отвергаются. Скрытого tie-break нет.
4. Перепроверить semantic owner, protected state и выбранную кривую;
   получить typed IDrawingObject и typed существующую выноску с exact refs.
   После разрешения объектов ещё раз проверить владельца и protected state.
   Вызвать setter один раз; строго проверить BOOL; затем собственный Update
   со строгим BOOL. False/None не превращать в success по соседнему getter.
5. Свежий GetBaseObject должен быть exact+Valid. Нужен действующий type12
   с доказанной принадлежностью ответвлению. Нельзя автоматически считать
   native constraint.Index=0 наконечником: collector должен отдельно установить
   соответствие (например, проверенный single-branch сценарий).
   Пустой Partner записывается; непустой противоречащий Partner отвергается.
6. Сверить все позы, матрицы, источники, полную проекционную геометрию по digest
   без numeric refs, print/visibility видов, print слоёв,
   typed field/UUID/tips/shelf/style, защищённый payload и immutable file SHA.
   Изменение Scale, включая 0, сохраняется в диагностике. Helper не скрывает
   его восстановлением. Успех: `structural_binding_verified_in_adapter`,
   `saved=False`, `persistence_verified=False`, `dynamics_verified=False`.

Guard проверяет свежие процесс/документ/path/RO/lease, фактическую версию v25,
active drawing и revision исходной модели до/после каждого callback. Это
обязательство native adapter, а не право принять исторический PID или receipt.
COM-объекты остаются на одном эксклюзивном STA. Только два resolve callback
возвращают typed объекты; остальные возвращают detached данные. Генераторы
с ленивыми COM getters запрещены. Native collector сам ограничивает получение
детей/проекций до материализации DTO. Пределы helper не прерывают зависший COM-call.

Снимки должны быть полными. DTO не может доказать, что collector не пропустил
вид или файл. Сравнение состояния точное; согласованная численная нормализация,
если нужна, задаётся collector заранее одинаково для baseline/readback и не
может исключать Scale, matrix, printability или другие защищённые поля.

Неопределённая ошибка после входа в setter оставляет `mutation_possible=True`.
Receipt сохраняет события и сырые нормализованные результаты. Допускается один
guarded диагностический снимок. Нет retry, повторного setter, fallback segment,
автоматического restore/Save или усыновления текущего документа.

## Возврат вызова и сохранение

`normalize_automation_return` использует явный enum конкретных Automation
методов. Save принимает только None: вызов завершился, персистентность ещё не
доказана. Update/Create/SetBaseObject принимают только настоящий bool. Числа
0/1/-1 не приводятся к bool; HRESULT-wrapper обязан иметь отдельный адаптер.
Это не глобальная замена truthiness во всех инструментах и не контракт SaveAs
или любого произвольного Create/Update.

`assess_saved_leader_anchor` — чистая проверка согласованности свидетельств:
Save(void), Changed=False, close, два независимых последовательных RO open,
точный planned drawing path и sealed SHA, полные неизменные protected snapshots.
В каждом цикле заново подтверждаются UUID/owner/subtree, bounded traversal без
root-query и принадлежность выбранной свежей проекции точному запрошенному узлу.
Base сравнивается с новым ref **этого** цикла. Тип/геометрия кривой должны
совпасть с detached bound_curve исходной привязки. Пустой Partner допустим.
Результат — `persistence_evidence_consistent`, native acceptance остаётся pending.
Заполненные DTO, даже согласованные, не доказывают, что чтения действительно были.

Модуль не подтверждает точное положение вдоль длинной прямой, движение наконечника,
автоматическую перенумерацию, native скорость, внешний вид PDF или все изделия.
Предел nearest — только предел выбора кандидата, не допуск готового чертежа.

## Подготовленная native acceptance, выполнять только после handover

1. Свежая discovery CAD/VM/процесса/документов; выделенный STA и новые собственные
   синтетические копии с полными зависимостями. Чужие документы сохранить.
   Создать небольшой assembly с повторными вставками одного файла, line/circle
   в canonical и presentation видах, существующими typed positional leaders.
2. Отдельным collector реализовать Protocol: реальные касты IDrawingObject,
   fresh UUID -> row.Geometry, текущие occurrence paths/file/subtree/SHA и
   семантическое соответствие повторных экземпляров. Никакого basename fallback.
   Снять полный baseline, including printability и typed field/shelf/tips.
3. Одна line и одна circle, один ответвлённый объект за раз: -1, strict return,
   getter, constraints; не изменять исходники. Отдельный disposable negative
   пилот с segment 0 лишь для изучения контракта, без автоматического retry.
   Проверить typed field, UUID, native row lookup, отсутствие побочных изменений.
4. Save без assert на None. Проверить точный owned path, существование/ненулевой
   файл, Changed=False, фактический SHA. Закрыть только собственный документ.
   Два fresh RO-цикла с complete owner/query/curve/readback snapshots и тем же
   SHA до/после. Старые numeric refs не требовать. Заполнить saved evidence oracle.
5. **Отдельная динамика**, на ещё одной полной disposable копии: зафиксировать
   исходные placement и Fixed; изменить именно нужную реальную вставку, выполнить
   подтверждённый native placement update/rebuild/save и регенерацию проекции.
   Сначала независимо измерить ненулевое перемещение **материальной проекции**
   больше согласованной точности измерения. Неподвижная проекция означает
   непригодный stimulus, а не провал/успех привязки.
6. Сравнить tip delta с delta выбранной material point в общей системе координат
   по обеим координатам; проконтролировать точное место вдоль прямой, не только
   расстояние до бесконечной линии. Проверить свежие owner/base/constraints/UUID.
   Save/close/fresh RO в изменённом состоянии. Затем вернуть полную исходную
   matrix/Fixed, rebuild/save/reopen и доказать возврат проекции и наконечника.
   Перемещение всего вида или rebuild неизменной модели не заменяют этот тест.
7. Визуально проверить native и экспортированные PDF обоих состояний, включая
   наконечник, полку, пересечения, typed позицию и печатность. Результаты разделить:
   structural, persistence, dynamics, visual; не расширять одиночный пилот на все
   документы и версии. Context/Current пилот, если нужен, проводить отдельно,
   не внутри рабочего setter helper, и сначала воспроизвести на синтетике.

До этих испытаний динамика и native acceptance **не доказаны**. Offline-код не
занимает общую CAD-сессию и не меняет рабочие/frozen инженерные рецепты.

Поздние native pilots дали отрицательное следование при действующем base/type12:
view.Rebuild, CompleteRebuildDocument и RebuildDocument с ожиданием не помогли.
Дополнительный PointOnCurve не создался до source displacement; оборванный
receipt не подтверждает cleanup/restore. Последующий отдельный synthetic native
опыт после handover также дал отрицательный unique-source-revision результат;
см. [native сравнение](native-leader-source-revisions.md). Новый native job сейчас
не требуется, автоматическое следование не принято.
Подробности и исправление signed coordinate modes — в
[исследовании динамики](leader-anchor-dynamics-research.md).
