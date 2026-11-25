# Нативная синтетическая проверка Geometry и собственной СП

25.11.2026, КОМПАС-3D v25. После явной передачи общей сессии и свежей описи.
Один STA worker, только новые собственные synthetic файлы; инженерные входы,
установленный SDK и конфигурация не менялись. Итог ниже разделяет членство
Geometry, runtime Reference, постоянные UUID, текст и прочий payload.

## Проверенный результат

**Same-singleton Geometry setter не принят.** В испытанной вложенной сборке
он сохранил ссылку на целевое вхождение, но добавил к Geometry одной строки
ещё и родительскую подсборку. Поэтому составная проверка
`len(Geometry)==1 AND target.Reference==fresh.Reference` не прошла.
Это доказательство дополнительного членства, а не исчезновения целевого Reference.
Оба row.Update при этом вернули True. Изменённая RAM-копия не сохранялась.

**Без записи в Geometry** прямой FileName old → new / own Update дал новые
данные СП с сохранением её UUID и точных singleton-связей. Эти свойства и
изменённая геометрия подтверждены двумя отдельными SavedRO циклами. При этом
**полная сохранность payload не прошла**: у скрытой одинаковой строки номер
позиции нормализовался с 2 на 1. Save также записал собственную вложенную
подсборку. Эти побочные эффекты не скрыты и не считаются сохранением всей таблицы.

Производственный случай «actual properties новые, а текст СП старый» этим
fixture **не воспроизведён**. Автоматический force-resync существующих строк
для произвольного изделия не принят. Результат не разрешает менять рабочие изделия.

## Fixture и измерения

Источник A: призма 20×10×4 мм, объём 800 мм³; B: 26×10×4 мм, 1040 мм³.
Каждый источник вставлен в отдельную native source assembly. Product содержит
две одинаковые source-вставки; owner содержит product с RevealComposition=True.
Own model specification сформировала две строки: первая/видимая и последующая/
скрытая, обе с Sync=True, EditSourceObject=False и singleton Geometry.

| Проверка | Наблюдение |
|---|---|
| Baseline SaveRO | Оба UUID и точная Geometry-связь сохранены |
| Геометрия owner до/после замены | 1600 → 2080 мм³ |
| Перед Geometry setter | Обе target-связи exact singleton |
| После двух same-singleton setter / Update | Update=True; один target singleton, у другого target + parent |
| TopPart / MainTopPart | Совпали; EditObject=None |
| Raw IPart7 / typed IPart7 / IModelObject / IKompasAPIObject | Для данного объекта Reference совпали |
| GetObjectId → FindObjectById | Roundtrip вернул тот же Reference внутри текущей сессии |
| Direct-only SavedRO 1 / 2 | UUID, singleton membership, object ID, occurrence metadata key, pose/flags и properties подтверждены |
| Объём SavedRO 1 / 2 | 2080 / 2080 мм³ |
| Прочий текст | Формат/зона/количество/примечание сохранены; скрытая позиция 2 → 1 |

Runtime Reference после переоткрытия меняется. Его нужно сравнивать с **новым
разрешением вхождения в том же открытом документе**, а не с числом из прежней RO
сессии. В испытанном случае постоянные SP UUID и occurrence object ID сохранились.
Один source metadata key может повторяться у разных вставок: UUID источника
не заменяет полный occurrence path и проверку однозначности.

Семантика [MainTopPart](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument3d1_maintoppart.html)
отделяет верхний компонент от режима редактирования «на месте». Само наличие
этого свойства не объясняет наблюдённый extra parent; в данном тесте оба дерева
совпали. Эксперимент не доказывает поведение при иных исполнениях/edit contexts.

## Текстовый oracle и сохранение зависимостей

Первая direct-only попытка остановилась с текстовым assert. Offline-разбор raw
показал ошибку oracle: сравнивались колонки СП с IPart7.Name, где оставалось
`Synthetic source A`. Actual IPropertyKeeper property 5 и колонка уже содержали
`Synthetic source B`, property 4 — новое обозначение, FromSource=True для обоих.
Называть этот отказ доказательством stale SP text нельзя. Raw failed receipt
не переписывался; отдельная reconciliation сохранила ссылку на его SHA.
Нативные source replacements не повторялись ради исправления проверки.

По [IPropertyKeeper.GetPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_getpropertyvalue.html)
нужно различать actual property value/FromSource и имя, полученное другим
интерфейсом. Это не универсальный диагноз причин отличия IPart7.Name.

Следующая строгая проверка обнаружила запись двух собственных файлов: owner
и product. Leaf/source A/B остались побайтово прежними. Такое изменение вложенной
подсборки согласуется с [описанием замены компонентов](https://help.ascon.ru/KOMPAS/25/ru-RU/cm_instance_change_sources.html),
но исходный owner-only guard остаётся failed. Отдельный read-only аудит проверил
сохранённый результат с явным учётом этого writeback; общую сохранность исходников
из него выводить нельзя. Для рабочего сценария копировать нужно всё дерево.

При проверке всей таблицы после сохранения выявлена нормализация скрытой позиции.
Попытка на новой baseline отключить CalculatePosition открыла «Очищать позиции?».
После точного ответа «Нет» tuning.Update вернул False; кандидат остановлен ещё
при подготовке и адресно закрыт без сохранения. Отключение расчёта позиций не
принято. В текущем экспериментальном runner предусмотрен временный режим ответа
No с восстановлением прежнего HideMessage; эта доработка нативно повторно не
запускалась и не выдаётся за исправление False.

## Код и независимые проверки

- [Экспериментальный runner](../scripts/validate_specification_reference.py) сохраняет
  отдельные квитанции фаз, полные snapshots и ошибочные промежуточные результаты.
  Это исследовательский сценарий, не installed tool и не транзакция.
- [Fresh discovery](../scripts/discover_native_session.py) использует только
  GetActiveObject; не запускает CAD. Native receipts и config остаются private.
- [NativeOwnedSession](../scripts/native_owned_session.py) по умолчанию требует
  чистые RO inputs. Явный preserve_exact_state допускает предсуществующий dirty
  документ только с точной fresh process identity, refs/state и pinned disk SHA;
  его нельзя сохранять/закрывать или присваивать ему владение SDK.
- [row_binding](../src/kompas_mcp/row_binding.py) теперь сохраняет фактические
  geometry references и отличает extra membership от ненаблюдаемого ожидаемого
  Reference. Ни один диагноз не ослабляет exact singleton gate и не утверждает
  семантическую потерю связи по одному несовпадению runtime refs. Native adapter
  и общая интеграция по-прежнему не приняты.

Все собственные документы закрыты. Финальная отдельная attach-only опись
совпала с исходной по process identity, refs/path/type/Changed/ReadOnly/Visible,
Active и SHA открытого чужого файла. Предсуществующий writable Changed=True
документ остался в том же состоянии; 22 файла защищённого дерева и 68 файлов
SDK/package проверены неизменными. Чужие Save/Rebuild/Close не вызывались.

Private evidence manifest и точные raw пути находятся в собственном SDK handoff,
вне публичного форка. Сохранены failed same-geometry, ошибочный text oracle,
owner-only writeback gate, position gate и failed tuning setup; успешный
read-only аудит их не заменяет. Производственная приёмка/визуальная проверка
выдачи не заявляются. Новый нативный запуск требует отдельной координации.
