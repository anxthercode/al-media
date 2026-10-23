from __future__ import annotations

from PySide6.QtCore import QObject, Slot

from al_media.i18n import tr

# Existing engine translations remain authoritative. New UI strings are kept in
# one four-language table, rather than embedded in individual QML controls.
ROWS = {
    "start_link": ("Download video or audio", "Скачайте видео или аудио", "Спампуйце відэа ці аўдыя", "Завантажте відео чи аудіо"),
    "start_help": (
        "Paste a link in the field above, then choose the format and quality.",
        "Вставьте ссылку в поле выше, затем выберите формат и качество.",
        "Устаўце спасылку ў поле вышэй, затым выберыце фармат і якасць.",
        "Вставте посилання в поле вище, потім виберіть формат і якість.",
    ),
    "link_placeholder": ("Paste a video or audio link", "Вставьте ссылку на видео или аудио", "Устаўце спасылку на відэа ці аўдыя", "Вставте посилання на відео чи аудіо"),
    "analyzing": ("Analyzing link…", "Анализируем ссылку…", "Аналізуем спасылку…", "Аналізуємо посилання…"),
    "analyzing_help": (
        "Getting file details and available formats. This usually takes a few seconds.",
        "Получаем сведения о файле и доступных форматах. Обычно это занимает несколько секунд.",
        "Атрымліваем звесткі пра файл і даступныя фарматы. Звычайна гэта займае некалькі секунд.",
        "Отримуємо відомості про файл і доступні формати. Зазвичай це триває кілька секунд.",
    ),
    "batch_help": (
        "The links will be added to your downloads using the current settings.",
        "Ссылки будут добавлены в загрузки с текущими настройками.",
        "Спасылкі будуць дададзены ў спампоўванні з бягучымі наладамі.",
        "Посилання буде додано до завантажень із поточними налаштуваннями.",
    ),
    "analysis_failed": ("Could not load file details", "Не удалось получить данные", "Не ўдалося атрымаць звесткі", "Не вдалося отримати дані"),
    "analysis_failed_help": ("Check the link and try again.", "Проверьте ссылку и повторите попытку.", "Праверце спасылку і паспрабуйце яшчэ раз.", "Перевірте посилання та спробуйте ще раз."),
    "jobs_files": ("Your downloads", "Ваши загрузки", "Вашы спампоўванні", "Ваші завантаження"),
    "queue_empty": ("Your downloads will appear here", "Здесь появятся ваши загрузки", "Тут з’явяцца вашы спампоўванні", "Тут з’являться ваші завантаження"),
    "crop": ("Trim", "Обрезать", "Абрэзаць", "Обрізати"),
    "whole_file": ("Entire file", "Весь файл", "Увесь файл", "Увесь файл"),
    "range_pending": ("Apply or reset the edited range", "Примените или сбросьте изменённый диапазон", "Ужыйце ці скіньце зменены дыяпазон", "Застосуйте або скиньте змінений діапазон"),
    "from": ("From", "С", "З", "Від"),
    "to": ("To", "До", "Да", "До"),
    "time_hours": ("Hours", "Часы", "Гадзіны", "Години"),
    "time_minutes": ("Minutes", "Минуты", "Хвіліны", "Хвилини"),
    "time_seconds": ("Seconds", "Секунды", "Секунды", "Секунди"),
    "reset": ("Reset", "Сбросить", "Скінуць", "Скинути"),
    "change_folder": ("Change folder", "Изменить папку", "Змяніць папку", "Змінити теку"),
    "browse": ("Browse…", "Обзор…", "Агляд…", "Огляд…"),
    "recent": ("Recent folders", "Недавние папки", "Нядаўнія папкі", "Нещодавні теки"),
    "ask_destination": ("Ask before each download", "Спрашивать перед каждым скачиванием", "Пытацца перад кожным спампоўваннем", "Запитувати перед кожним завантаженням"),
    "saving": ("Downloading and saving", "Загрузка и сохранение", "Спампоўванне і захаванне", "Завантаження та збереження"),
    "audio_files": ("Audio files", "Аудиофайлы", "Аўдыяфайлы", "Аудіофайли"),
    "saved": ("Saved", "Сохранено", "Захавана", "Збережено"),
    "concurrency_invalid": ("Enter a number from 1 to 5", "Введите число от 1 до 5", "Увядзіце лік ад 1 да 5", "Введіть число від 1 до 5"),
    "settings_error": ("Could not save settings", "Не удалось сохранить настройки", "Не ўдалося захаваць налады", "Не вдалося зберегти налаштування"),
    "example": ("Example", "Пример", "Прыклад", "Приклад"),
    "close": ("Close", "Закрыть", "Закрыць", "Закрити"),
    "details": ("Details", "Подробнее", "Падрабязней", "Докладніше"),
    "batch": ("Links ready to add", "Ссылки готовы к добавлению", "Спасылкі гатовыя да дадання", "Посилання готові до додавання"),
    "no_preview": ("Preview unavailable", "Предпросмотр недоступен", "Перадпрагляд недаступны", "Попередній перегляд недоступний"),
    "more_tracks": ("Tracks and subtitles", "Дорожки и субтитры", "Дарожкі і субтытры", "Доріжки та субтитри"),
    "select_items": ("Select playlist items", "Выберите элементы плейлиста", "Выберыце элементы плэйліста", "Виберіть елементи списку"),
    "choose_folder": ("Download destination", "Папка для скачивания", "Папка для спампоўвання", "Тека для завантаження"),
    "clear_link": ("Clear link", "Очистить ссылку", "Ачысціць спасылку", "Очистити посилання"),
    "save_folder": ("Download folder", "Папка для скачивания", "Папка для спампоўвання", "Тека для завантаження"),
    "repeat_question": ("A matching task already exists. Download again?", "Такое задание уже существует. Скачать ещё раз?", "Такое заданне ўжо існуе. Спампаваць яшчэ раз?", "Таке завдання вже існує. Завантажити ще раз?"),
    "supported_sources": ("Supported sources", "Поддерживаемые источники", "Крыніцы, якія падтрымліваюцца", "Підтримувані джерела"),
    "all_sites": ("All supported sites", "Все поддерживаемые сайты", "Усе сайты, якія падтрымліваюцца", "Усі підтримувані сайти"),
    "developer": ("Developer", "Разработчик", "Распрацоўшчык", "Розробник"),
}


def text(language: str, key: str) -> str:
    if key in ROWS:
        return ROWS[key][{"en": 0, "ru": 1, "be": 2, "uk": 3}.get(language, 1)]
    return tr(language, key)


class Localization(QObject):
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences = preferences

    @Slot(str, result=str)
    def text(self, key: str) -> str:
        return text(self.preferences.language, key)
