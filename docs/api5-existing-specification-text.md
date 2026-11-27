# API5: текст существующих строк собственной model specification

26.11.2026. Узкий нативный результат другого владельца CAD-сессии на отдельной
копии, КОМПАС v25. SDK-чат выполнил только offline-сверку сохранённой квитанции:
сравнил полные before/after payload, UUID-ключи, сырые результаты вызовов и статусы
двух SavedRO проверок. Независимого live attach или повторного native опыта здесь
не было. Инженерные файлы, строки изделий, их UUID и private receipt в репозиторий
не включены; точный источник и SHA оставлены в собственном private handoff.

## Что принято и что остаётся открытым

**Прямое редактирование текста существующих собственных строк через API5 принято
для испытанной копии**, включая скрытые одинаковые строки. Изменились только
заданные колонки обозначения/наименования. Полный остальной payload, прежние
позиции, флаги, UUID и singleton Geometry сохранены; два SavedRO прошли по квитанции.
Владелец также подтвердил сохранение actual properties/FromSource, дерева и
исходников. Записан только canonical owner A3D.

Это **text authoring**, а не автоматический properties-resync или подтверждение
будущего динамического следования свойствам. Нативный путь не назначает причину
прежнего API7 row.Update=False и не исправляет Geometry setter. Общий native
adapter/инструмент MCP для этого пути не установлен. Позднее добавлен отдельный
helper с внедряемым adapter и строгими gates; его собственные
[synthetic literal-text проверки](native-specification-text.md) отклонены из-за
regrouping/изменения свойств. Они не являются повтором принятого stale-text случая.
Произвольные стили, исполнения и внешние inherited строки не приняты.

## Exact owner и описание

У exact API5 [ksDocument3D.GetSpecification()](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksdocument3d_getspecification.html)
нет аргументов; он возвращает LPDISPATCH `ksSpecification`. Получать его нужно у
проверенного документа-владельца, а не у случайного активного документа или SPW.
API7→API5 document lookup по уже установленному Reference не означает, что можно
использовать Reference строки как API5 spcObj.

Выбор описания проверяется по библиотеке стилей, StyleID и имени подключённой СП.
[API7 desc.Active=True](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationdescription_active.html)
делает описание текущим без description.Update; поставить Active=False нельзя.
API5 [ksGetSpcDescription](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcdescription.html)
читает параметры и состояние: `long (long index, LPDISPATCH param, BOOL* state)`.
У [ksSpcDescrParam](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspcdescrparam_props.html)
поля называются `layoutName`, `styleId`, `spcName`.

В принятом опыте использован **явно установленный индекс** и подтверждены return=1,
state=True и все поля описания. Хотя SDK документирует index=-1 как current,
отдельная проба исполнителя вернула 0 при state=True и подходящих полях. Это не
успех и не установленный общий баг: поля при неуспешном возврате не заменяют
проверку результата. Индексы API5/API7 и StyleID не взаимозаменяемы.

При необходимости [ksSetSpcDescription(index, NULL, TRUE)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_kssetspcdescription.html)
документирован как переключение состояния без замены параметров стиля.
[ksSetCurrentSpcObject](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_kssetcurrentspcobject.html)
ограничен видимыми таблицами; он не был назначен обязательным шагом hidden modeldesc.
Новые описания и строки для этой операции не создаются.

## Numeric bridge и text editing

Сначала выбирается существующая API7 строка по exact UUID. Её
[UniqueNumber](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationobject_uniquenumber.html)
имеет тип double; не превращать его в long, номер позиции или индекс строки.
[ksGetSpcObject(double objNumb)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobject.html)
возвращает API5 long spcObj. В принятом опыте проверено обратное отображение
[ksGetSpcObjectNumber(long spcObj)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobjectnumber.html)
и совпадение с исходным UniqueNumber в том же owner/description.

Перед изменением [ksGetSpcObjectColumnText](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobjectcolumntext.html)
сравнивается с API7 текстом **той же строки и колонки**. Getter принимает spcObj,
columnType, ispoln и block; setter spcObj не принимает — использует edit context.
В испытанном стандартном стиле колонки 4/5 подтверждены при ispoln=1, block=0.
Эти адреса не назначаются автоматически произвольным стилям/исполнениям.

| Вызов Automation v25 | Контракт |
|---|---|
| [ksSpcObjectEdit(long spcObj)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksspcobjectedit.html) | long: 1 — успех, 0 — отказ |
| [ksSetSpcObjectColumnText(long columnType, long ispoln, long block, BSTR str)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_kssetspcobjectcolumntext.html) | long: 1 — успех; записывает текст в текущий редактируемый объект |
| [ksSpcObjectEnd()](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksspcobjectend.html) | long **указатель объекта**, не BOOL и не success==1 |

В квитанции все Edit/Set вернули 1; End вернул прежний указатель. Это наблюдение
одного опыта, не универсальная гарантия неизменности runtime pointer. Проверки
UUID/UniqueNumber/Geometry и полного payload после End обязательны независимо
от числового результата. Python out/tuple форму брать из installed makepy,
не угадывать по одному синтаксису C.

Не вызывались API7 row.Update/Edit, Geometry setter, ClearGeometry, IncludeGeometry,
создание строк или изменение группировки ради обхода отказа. Текст взят из заранее
проверенных actual properties; это явный текстовый план с конечным набором ячеек.

## Область приёмки и сохранённые ограничения

- Строки собственного owner, State=ssIndependent, Sync=True/EditSourceObject=False;
  обработаны и видимые first, и скрытые subsequent одинаковые строки.
- Полный UUID-набор и все флаги/колонки сравниваются, разрешены только заранее
  объявленные изменения текста. Existing позиции не перерассчитываются.
- Владелец проверил прежние singleton links и дерево; Save вызван один раз,
  его void-результат None не проверялся на truthiness.
- Два SavedRO записаны успешными для точного payload и Geometry; changed-files
  содержит только target owner, исходный набор отмечен неизменным.

Предыдущие [synthetic Geometry/numbering failures](native-specification-reference.md)
остаются отрицательными и не заменяются этой приёмкой другой операции. При новом
применении отдельно проверять FromSource и границы записи зависимостей: обычная
правка текста может быть переопределением, а не восстановлением source inheritance.
Один правильный текст или Edit/Set=1 не являются достаточным gate.
