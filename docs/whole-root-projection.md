# Быстрый сбор геометрии целого изделия: оценка применимости

23.11.2026. Исследован переданный инертный `root_projection_geometry.py`;
он не импортировался и не исполнялся. Рабочие native recipes не менялись.
В SDK добавлен только чистый offline evaluator `assess_whole_root_projection`
в `root_projection.py`; интеграции с CAD или автоматического fast-path нет.

## Вывод

Прямой обход LineSegments/Circles/Arcs контейнера вида — перспективный способ
избежать повторных AssociationObjects по дереву компонентов, **если весь
источник вида является точным нужным изделием**. Он даёт геометрию всего вида,
а не доказательство принадлежности отдельной детали внутри большей сборки.
Для leaf/subassembly selection в чужом полном источнике этот путь запрещён.

Совпадения basename, принадлежности файла где-то в subtree и одного общего SHA
недостаточно. При переносе целого изделия в presentation source допускается
точная SHA-equivalence двух полных файлов по разным абсолютным путям, только
вместе с текущим UUID/row.Geometry owner и явным semantic instance mapping.
Подмена изделия его дочерней деталью не проходит whole-product gate.

Переданный helper правильно отделяет whole-view scope от component membership,
не вызывает AssociationObjects(root), ограничивает сумму трёх коллекций до
обхода, сверяет owner/mode/flags и сохраняет sweep дуги. Его нельзя сразу
объявлять принятым общим native collector:

- bool()/int()/float() могут скрывать неверный тип API getter. Новый DTO-контракт
  требует strict bool/count/mode и конечные координаты.
- Flags и owning view сами по себе не доказывают происхождение material curve:
  crop/construction/generated объекты требуют независимой классификации.
  Неизвестная классификация пригодного кандидата блокирует результат.
- Равенство полного файла не различает повторные semantic instances. Нужны
  pinned occurrence mapping, actual UUID row.Geometry и полный current source.
- Частичный повтор getter недостаточен для обнаружения всех побочных изменений.
  Новый контракт сравнивает полные before/after source/root/view/print snapshots,
  включая RO, Valid, model revision, projection geometry и обе view identities.
- Возвращаемые native объекты не являются переносимым кэшем. В общем SDK индекс
  хранит detached DTO; позднее выбранный объект заново разрешается в owning STA.

## Offline-контракт

`RootProjectionPlan` требует target.path=[] и явный special MainTopPart.
Target.component_file должен быть полным source model file с тем же SHA;
canonical.component SHA должен совпасть с этим whole-product SHA. В presentation
canonical member path должен быть **самим** owner, не его потомком. Полный
source path/hash owning view совпадает с target model. SemanticScope сохраняет
ограничения [контракта выносок](existing-leader-anchors.md).

Evidence содержит:

1. Полные одинаковые snapshots до/после: fresh row.Geometry owner, exact root ref,
   model doc/ref/path, current disk SHA и отдельно доказанную загруженную ревизию,
   RO=True/Changed=False, Valid root/view, exact view==association interface ref,
   positive native view number, все protected poses/matrices/geometry/print fields.
2. Inventory counts всех трёх коллекций до чтения элементов. Их сумма ограничена,
   включая будущие rejected/excluded entries и arcs. Кандидаты содержат **все**
   raw entries; количество по каждому typed kind обязано совпасть. Нет молчаливого
   truncation. Повтор native ref внутри/между коллекциями — отказ, а не dedup.
3. Для каждого пригодного кандидата — Valid/notTemp/visible/association/curve/
   geometry, exact owner view и coordinate mode. Для material необходима явная
   `source_projection` классификация с отдельным evidence digest. Для исключения
   crop/construction нужна текущая классификация, совпадающая с pinned whitelist;
   отсутствующий/stale ref или исключение source_projection отвергаются.
4. Arc хранит xc/yc/r, оба endpoint, Angle1/Angle2 и Direction. Arc никогда не
   преобразуется в полный circle. Здесь нет nearest-arc алгоритма; существующий
   mutation helper поддерживает только line/circle и автоматически не расширен.

Проверяются порядок inventory -> harvest -> final recheck и reported counters
AssociationObjects=0/component enumeration=0. Это проверка **свидетельств**,
а не наблюдение фактических native calls. Collector обязан сам ограничивать
получение raw элементов, измерять текущие hashes/loaded revision, не использовать
Current и выполнять fresh guards. Полноту и правдивость DTO этот evaluator
самостоятельно установить не может. Flags не заменяют проверку material lineage.

Результат: `whole_root_evidence_consistent`, scope=`whole_product_view_only`,
detached curves/rejection counts. Всегда component_membership_verified=False,
nearest_selection_performed=False, native_acceptance=pending, speedup_verified=False.
Индекс нельзя подставлять в AssociationObjects adapter как выдуманное доказательство
component membership. Существующий guarded child traversal остаётся без изменений.

## Подготовленная отдельная native проверка

После явной передачи CAD-ресурса — на synthetic owned copies:

1. Минимальный whole-product source и presentation copy с одинаковыми полными
   bytes, но разными путями; отдельная bigger assembly с повторными вставками
   того же файла. Whole-product случай разрешён; nearest leaf в bigger assembly,
   owner-descendant case, другой SHA/instance mapping должны отклоняться до scan.
2. Виды с line/circle/arc, crop, construction, invisible и temporary geometry.
   Проверить actual typed collection/getter контракты и independent material
   lineage. Сверить все допустимые кривые с сохранённым baseline; установить,
   что исключения не убирают реальную material geometry. При неизвестном
   происхождении прямой путь не использовать.
3. Сравнить с bounded child association harvest на том же источнике и pose:
   полноту геометрии и material points, не требуя сохранения numeric refs через
   reopen. Arc sweep/Direction проверить отдельно; не превращать его в circle.
4. Измерить общее время и отдельно calls/counts на независимых одинаковых copies:
   warm/cold состояние, число raw/accepted curves, casts/getters, SHA/guard время.
   Не сравнивать время полного старого batch с временем одного нового DTO-pass.
   До этих измерений уменьшение числа ожидаемых запросов — гипотеза ускорения.
5. Проверить before/after poses/matrices/geometry/printability и неизменные SHA;
   затем Save/RO/visual gates привязки при отдельной интеграции. Динамика требует
   самостоятельного displacement/restore испытания из плана выносок и не следует
   из скорости или nonempty collection.

Текущие native batch и установленный SDK этим изменением не затронуты.
