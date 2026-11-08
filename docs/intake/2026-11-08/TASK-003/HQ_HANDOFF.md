# OpDB Headquarters — TASK-003 Quality handoff

**Дата:** 2026-11-08. **От:** OpDB Quality, независимая проверка.

## Поставка

Пакет **OpDB Verification Lab 0.1**: `ADR-004.md` (PROPOSED), `TEST_MATRIX.md`, `verification_lab.py`, `cross_engine.py`, `tests/test_lab.py`, `.github/workflows/verification.yml`, отчёт и два raw JSON-файла. Файлы оформлены локально, **не опубликованы в GitHub, не направлены технически в другой чат**.

## Вердикт

- **PASS** на самостоятельном стенде: differential (1256 проверок), TLP/NoREC-подобные (30), 6000 journal changes с full-aggregate cutover, маленькая проверенная concurrent history, 2 process crashes, 5 paired SQLite performance trials; 6 `unittest` регрессий.
- **FAIL** для заведомо небезопасного cached Lens: внешний COMMIT Source меняет значение с 5 до 25, Lens сохраняет 5, integrity_check=ok. Прямой контрпример; **не подтверждение дефекта реального OpDB**.
- **NOT VERIFIED** для движка OpDB, Safety Proof Gate, Core, PostgreSQL/MySQL, GitHub CI и power-loss scenarios: в доступном окружении не было реального target репозитория, серверов PostgreSQL/MySQL, полного ADR-001 и самостоятельного ядра.

## Решения, которые требуются от Headquarters

1. Назначить статус ADR-004: PROPOSED → review Safety/Core → принят/исправлен с указанием конфликтов с ADR-001.
2. Объявить Q-001 обязательным regression gate для любого переключения Lens, включая внешние writer-ы, DDL, prepared statements, tamper.
3. Дать Quality disposable OpDB Core/Safety adapter из `ENGINE_ADAPTER_CONTRACT.md`, commit SHA, fault hooks, real R12 seed203 reproducer и актуальный ADR-001.
4. Разместить Lab в отдельном репозитории/каталоге; подключить workflow, закрепить обязательные проверки, собрать реальные CI artifacts.
5. До выполнения этих условий статус релизной готовности и ускорения **NOT VERIFIED**, оптимизация не разрешена по одному синтетическому бенчмарку.

## Научная добросовестность

Первый benchmark: SQLite no-index vs SQLite index, 5000 строк, 250 действий × 5 пар, медиана полного времени 46.94 vs 17.45 мс; парное время с индексом 0.368×. **Не OpDB.** Система с индексом ожидаемо выигрывает на данной селективной синтетике, но внешняя воспроизводимость и характеристики физического SSD не проверены.