# Результаты заданий и фазовые таймеры

Завершение Python-обёртки, проверка CAD-артефакта и фактическая приёмка — три
разных наблюдения. `failed_left_open` остаётся ошибкой даже при коде запуска 0.
Timeout и неизвестная фаза требуют сверки, а не автоматического повтора записи.

## Проверка сохранённого результата

```console
python -m kompas_mcp.job_results verify-result /owned/job/result.json --launcher-returncode 0
python -m kompas_mcp.job_results verify-result /owned/job/result.json --require-artifact-verification
```

Код возврата: 0 — известная успешная фаза выполнения; 1 — ошибка выполнения или
неверный SHA артефакта; 2 — неполные/неизвестные данные, timeout либо ошибка JSON.
Ключ `--require-artifact-verification` дополнительно требует явного
`verification.artifacts="verified"` и хотя бы одного актуально сверенного файла
из `artifacts`. Один SHA доказывает целостность файла, не правильность геометрии.
Состояние `physical_acceptance` от этого не меняется.

UTF-8 BOM допускается. Неизвестная версия schema, повторяющиеся ключи, NaN/Infinity,
неверные поля артефактов отклоняются. Прежние JSON без schema с известной фазой
поддержаны; обычный tool-ответ без фазы не выдаётся CLI за принятую CAD-операцию.

## Один runner для CLI и MCP

`JobResultStore(directory, job_id, metadata=None)` создаёт исключительно новый
подкаталог задания. Имеющийся job_id не перезаписывается. `result.json` заменяется
атомарно после flush/fsync; `events.jsonl` хранит последовательность снимков.
Завершённый результат неизменяем. Журнал событий — средство разбора; текущим
снимком остаётся `result.json`. Сбой между записью события и заменой снимка не
доказывает завершённую публикацию результата.

```python
from kompas_mcp.job_results import JobResultStore, phase

store = JobResultStore("owned-results", "job-unique", {
    "input_sha256": "<actual digest>",
    "runtime_fingerprint": "<actual loaded runtime digest>",
    "application": {"pid": "<observed PID>", "creation_time": "<observed creation>"},
})
store.write("running")
with store.timer.span("job"):
    with phase("source_hash", counts={"files": 4}):
        pass
store.write("complete_closed", verification={"artifacts": "not_verified"},
            owned_documents=[])
```

Поля выше должен заполнить runner реальными наблюдениями. Отсутствующие input SHA,
runtime/application identity, ledger и проверки не синтезируются. В persisted JSON
передаются только JSON-значения; COM-объекты и неконечные числа отклоняются.

`mark_timeout()` пишет `reconciliation_required`, не отменяет native-вызов,
не закрывает документы и не разрешает повтор. После наблюдаемого завершения именно
этого задания можно записать его итог; для нового выполнения нужен новый job_id.

## Интеграция worker

`ComWorker(..., result_directory=None, runtime_metadata=None)` сохраняет прежнюю
однопоточную STA и очередь. Переменная `KOMPAS_MCP_JOB_DIR` включает durable receipts
при отсутствии явно переданного каталога. Если ни каталог, ни переменная не заданы,
записей на диск нет. `call(..., metadata=None)` передаёт наблюдённые сведения входа;
`runtime_metadata` передаётся отдельно. Пустые metadata не являются доказательством
идентичности исходников/загруженного runtime.

Known failure phase возвращённого словаря даёт в `job_status` state=`failed`,
`result_phase` и отдельные статусы выполнения/проверок. Старые generic-ответы
возвращаются как раньше: state=`completed` означает завершение обёртки, при этом
execution_status=`unreported` и artifact_verification_status=`not_verified`.
Ошибка сохранения receipt видна в статусе и выбрасывается вызывающему после
выполнения native-вызова; это не основание повторять его.
Во время сохранения receipt state=`persisting_result`, pending ещё занят;
job не вытесняется из ограниченной истории до окончания этой записи.
Завершение native Future предшествует его callbacks, поэтому `call` отдельно ждёт
publication-completion Future через `asyncio.shield`. Даже позднее подключение
ожидания к уже завершённому native Future не возвращает успех до записи receipt;
поздняя ошибка диска передаётся вызывающему. Отмена ожидания не отменяет публикацию.
`wrapper_status` отдельно показывает, завершился ли сам callback без исключения:
он может быть `completed` одновременно с execution_status=`failed` у возвращённого
`failed_left_open`. Эти наблюдения не заменяют друг друга.

Ограниченная история worker может быть вытеснена; файлы собственных заданий
при этом сохраняются. Cancel по-прежнему отменяет только ещё не начатое задание.
Native-вызов и владение документами не передаются в другой поток.

## Измерение этапов

`PhaseTimer.span(name, counts=None, cache_hit=False, metadata=None)` использует
монотонные наносекунды и context-local родителя. `phase(name, **metadata)` находит
текущий таймер внутри worker/runner, а вне него ничего не делает. Это позволяет
инструментировать open/save/rebuild/export без изменения backend-сигнатур.

Snapshot включает inclusive elapsed, exclusive duration с вычитанием объединения
дочерних интервалов и union wall time корней. Суммировать все inclusive spans нельзя.
Cache hits и счётчики — отдельные поля, не обещание ускорения. Эти тесты проверяют
контракт Python; правильность native-геометрии и быстродействие CAD ими не доказаны.
