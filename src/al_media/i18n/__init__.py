from __future__ import annotations

from .desktop import BE_ERRORS, LANGUAGES, ROWS
from .interface import UI_TEXT

TEXT = {
    "ru": {
        "downloads": "Загрузки", "history": "История", "settings": "Настройки", "about": "О программе",
        "paste": "Вставить", "add": "Добавить", "all": "Скачать всё", "start": "Начать",
        "cancel": "Отменить", "retry": "Повторить", "remove": "Убрать из списка",
        "open": "Открыть файл", "folder": "Показать в папке", "choose": "Выбрать…",
        "update": "Проверить / обновить yt-dlp", "logs": "Открыть папку логов",
        "empty": "Вставьте ссылку или перетащите .txt файл", "path": "Папка загрузки",
        "concurrency": "Одновременные загрузки", "theme": "Тема", "language": "Язык",
        "subtitles": "Скачивать субтитры", "metadata": "Встраивать метаданные",
        "thumbnail": "Встраивать обложку", "updates": "Проверять обновления при запуске",
        "cookies": "Cookies", "clear_cookies": "Очистить настройки cookies",
        "configure_access": "Настроить доступ",
        "cookies_help": "Если сайт требует входа, выберите browser и браузер, где у вас есть доступ, "
                        "или укажите файл cookies.txt. Сохраните настройки и повторите задачу. Не передавайте cookies другим.",
        "pending_metadata": "Ожидает метаданные", "fetching_metadata": "Получение информации…", "metadata_unavailable": "Информация о видео недоступна",
        "ready": "Готово к загрузке", "queued": "В очереди", "downloading": "Загрузка",
        "postprocessing": "Объединение / конвертация", "completed": "Готово",
        "failed": "Ошибка", "cancelled": "Отменено", "interrupted": "Прервано",
        "error_unsupported_url": "Ссылка не поддерживается yt-dlp.",
        "error_youtube_verification": "YouTube просит подтвердить, что вы не бот. Настройте cookies для своего аккаунта и повторите задачу.",
        "error_cookies_unreadable": "Не удалось прочитать cookies браузера. Выберите другой доступный браузер или файл cookies.txt.",
        "error_private_media": "Видео закрыто. Для загрузки нужен разрешённый доступ к нему.",
        "error_auth_required": "Сайт требует авторизацию. Настройте cookies для аккаунта с доступом и повторите задачу.",
        "error_unavailable": "Видео недоступно. Проверьте ссылку и доступ к нему.",
        "error_geo": "Видео недоступно в вашем регионе.",
        "error_rate_limit": "Сайт ограничил частоту запросов. Попробуйте позже.",
        "error_ffmpeg": "Ошибка FFmpeg. Проверьте компоненты приложения.",
        "error_deno": "Ошибка Deno или JavaScript. Проверьте компоненты приложения.",
        "error_disk_full": "На диске недостаточно места.",
        "error_folder_denied": "Нет доступа к папке загрузки.",
        "error_network": "Ошибка сети или истекло время ожидания.",
        "error_engine": "Ошибка yt-dlp. Откройте папку логов или повторите позже.",
        "error_engine_missing": "yt-dlp отсутствует или повреждён.",
        "error_invalid_metadata": "Сайт вернул некорректные метаданные.",
        "error_final_file_missing": "Загрузка завершилась без итогового файла.",
        "error_no_formats": "Нет доступных форматов для загрузки.",
        "error_folder_unavailable": "Папка загрузки недоступна.",
    },
    "en": {
        "downloads": "Downloads", "history": "History", "settings": "Settings", "about": "About",
        "paste": "Paste", "add": "Add", "all": "Download all", "start": "Start",
        "cancel": "Cancel", "retry": "Retry", "remove": "Remove from list",
        "open": "Open file", "folder": "Show in folder", "choose": "Choose…",
        "update": "Check / update yt-dlp", "logs": "Open log folder",
        "empty": "Paste a link or drop a .txt file", "path": "Download folder",
        "concurrency": "Concurrent downloads", "theme": "Theme", "language": "Language",
        "subtitles": "Download subtitles", "metadata": "Embed metadata",
        "thumbnail": "Embed cover", "updates": "Check updates on startup",
        "cookies": "Cookies", "clear_cookies": "Clear cookie settings",
        "configure_access": "Configure access", "cookies_help": "If a site requires sign-in, choose browser and a browser with access, or select a cookies.txt file. Save settings and retry the task. Never share your cookies.",
        "pending_metadata": "Pending metadata", "fetching_metadata": "Loading metadata…", "metadata_unavailable": "Video information unavailable",
        "ready": "Ready", "queued": "Queued", "downloading": "Downloading",
        "postprocessing": "Merging / converting", "completed": "Completed",
        "failed": "Failed", "cancelled": "Cancelled", "interrupted": "Interrupted",
        "error_unsupported_url": "yt-dlp does not support this URL.",
        "error_youtube_verification": "YouTube asks you to confirm you are not a bot. Configure cookies for your account and retry.",
        "error_cookies_unreadable": "Browser cookies could not be read. Choose another available browser or a cookies.txt file.",
        "error_private_media": "This video is private. Access to it is required.",
        "error_auth_required": "The site requires sign-in. Configure cookies for an account with access and retry.",
        "error_unavailable": "This video is unavailable. Check the link and your access.",
        "error_geo": "This video is unavailable in your region.",
        "error_rate_limit": "The site is rate limiting requests. Try again later.",
        "error_ffmpeg": "FFmpeg failed. Check the bundled tools.",
        "error_deno": "Deno or JavaScript failed. Check the bundled tools.",
        "error_disk_full": "The disk is full.",
        "error_folder_denied": "The download folder is not accessible.",
        "error_network": "Network error or timeout.",
        "error_engine": "yt-dlp failed. Open the log folder or try again later.",
        "error_engine_missing": "yt-dlp is missing or damaged.",
        "error_invalid_metadata": "The site returned invalid metadata.",
        "error_final_file_missing": "The final download file was not found.",
        "error_no_formats": "No downloadable formats are available.",
        "error_folder_unavailable": "The download folder is unavailable.",
    },
    "uk": {
        "downloads": "Завантаження", "history": "Історія", "settings": "Налаштування", "about": "Про програму",
        "paste": "Вставити", "add": "Додати", "all": "Завантажити все", "start": "Почати",
        "cancel": "Скасувати", "retry": "Повторити", "remove": "Прибрати зі списку",
        "open": "Відкрити файл", "folder": "Показати у теці", "choose": "Обрати…",
        "update": "Перевірити / оновити yt-dlp", "logs": "Відкрити теку журналів",
        "empty": "Вставте посилання або перетягніть .txt файл", "path": "Тека завантажень",
        "concurrency": "Одночасні завантаження", "theme": "Тема", "language": "Мова",
        "subtitles": "Завантажувати субтитри", "metadata": "Вбудовувати метадані",
        "thumbnail": "Вбудовувати обкладинку", "updates": "Перевіряти оновлення під час запуску",
        "cookies": "Cookies", "clear_cookies": "Очистити налаштування cookies",
        "configure_access": "Налаштувати доступ", "cookies_help": "Якщо сайт вимагає входу, виберіть browser і браузер із доступом або файл cookies.txt. Збережіть налаштування й повторіть завдання. Не передавайте cookies іншим.",
        "pending_metadata": "Очікує метадані", "fetching_metadata": "Отримання інформації…", "metadata_unavailable": "Інформація про відео недоступна",
        "ready": "Готово до завантаження", "queued": "У черзі", "downloading": "Завантаження",
        "postprocessing": "Об’єднання / конвертація", "completed": "Готово",
        "failed": "Помилка", "cancelled": "Скасовано", "interrupted": "Перервано",
        "error_unsupported_url": "yt-dlp не підтримує це посилання.",
        "error_youtube_verification": "YouTube просить підтвердити, що ви не бот. Налаштуйте cookies свого облікового запису й повторіть.",
        "error_cookies_unreadable": "Не вдалося прочитати cookies браузера. Виберіть інший доступний браузер або файл cookies.txt.",
        "error_private_media": "Відео приватне. Для завантаження потрібен дозволений доступ.",
        "error_auth_required": "Сайт вимагає входу. Налаштуйте cookies облікового запису з доступом і повторіть.",
        "error_unavailable": "Відео недоступне. Перевірте посилання та доступ.",
        "error_geo": "Відео недоступне у вашому регіоні.",
        "error_rate_limit": "Сайт обмежив частоту запитів. Спробуйте пізніше.",
        "error_ffmpeg": "Помилка FFmpeg. Перевірте компоненти програми.",
        "error_deno": "Помилка Deno або JavaScript. Перевірте компоненти програми.",
        "error_disk_full": "На диску бракує місця.",
        "error_folder_denied": "Немає доступу до теки завантаження.",
        "error_network": "Помилка мережі або час очікування вичерпано.",
        "error_engine": "Помилка yt-dlp. Відкрийте теку журналів або повторіть пізніше.",
        "error_engine_missing": "yt-dlp відсутній або пошкоджений.",
        "error_invalid_metadata": "Сайт повернув некоректні метадані.",
        "error_final_file_missing": "Підсумковий файл завантаження не знайдено.",
        "error_no_formats": "Немає доступних форматів для завантаження.",
        "error_folder_unavailable": "Тека завантаження недоступна.",
    },
}


for language, labels in UI_TEXT.items():
    TEXT[language].update(labels)

TEXT["be"] = dict(BE_ERRORS)
for key, values in ROWS.items():
    for (_name, language), value in zip(LANGUAGES, values, strict=True):
        TEXT[language][key] = value


def tr(language: str, key: str) -> str:
    return TEXT.get(language, TEXT["ru"]).get(key, TEXT["en"].get(key, key))


def format_label(language: str, key: str, max_height: int | None = None) -> str:
    if key == "best" and max_height:
        return f"{max_height}p — {tr(language, 'best_quality')}"
    if key.startswith("video:"):
        height = int(key.split(":")[1])
        return f"{height}p" + (f" — {tr(language, 'best_quality')}" if height == max_height else "")
    if key.startswith("mp3:"):
        rate = key.split(":")[1]
        return f"MP3 · {rate} {tr(language, 'kbps')}"
    return {"best": tr(language, "best_available"), "audio": tr(language, "source_audio"), "m4a": "M4A", "mp4": "MP4"}.get(key, key)
