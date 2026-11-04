from PySide6.QtCore import QLocale, QTimeZone

from launcher import config


def detect_donate_link() -> tuple[str, str]:
    locale = QLocale.system()
    is_cis_locale = locale.language() in (
        QLocale.Language.Ukrainian,
        QLocale.Language.Russian,
    ) or locale.country() in (
        QLocale.Country.Ukraine,
        QLocale.Country.Russia,
        QLocale.Country.Belarus,
    )

    timezone_id = QTimeZone.systemTimeZoneId().data().decode("utf-8", errors="ignore")
    is_cis_timezone = any(
        marker in timezone_id
        for marker in ("Kiev", "Kyiv", "Ukraine", "Moscow", "Minsk", "FLE", "GTB")
    )

    donate = config.SOCIAL_CONFIG["donate"]
    if is_cis_locale or is_cis_timezone:
        return donate["link_ua"], "Підтримати розробку"
    return donate["link_global"], "Support development"
