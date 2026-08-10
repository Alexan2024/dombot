"""All user-facing texts in Russian and English.

Use t(lang, key, **kwargs) to fetch and format a string.
HTML formatting is used (bot runs with parse_mode=HTML).
"""
from config import RESTAURANT_NAME

T = {
    "ru": {
        # --- language / start ---
        "choose_language": (
            f"🇷🇺 Добро пожаловать в <b>{RESTAURANT_NAME}</b>\n"
            f"🇬🇧 Welcome to <b>{RESTAURANT_NAME}</b>\n\n"
            "Выберите язык / Choose your language"
        ),
        # --- main menu ---
        "main_menu": (
            f"Рады видеть вас в <b>{RESTAURANT_NAME}</b>\n"
            "Чем можем помочь?"
        ),
        "btn_book": "📅 Забронировать стол",
        "btn_menu": "📖 Меню",
        "btn_events": "🎭 Афиша",
        "btn_hours": "📍 Часы и адрес",
        "btn_faq": "❓ Вопросы",
        "btn_language": "🌐 Язык / Language",
        # --- booking flow ---
        "ask_date": (
            "На какую дату хотите забронировать стол?\n\n"
            "Нажмите «Сегодня» или «Завтра», либо напишите свою дату "
            "в формате ДД.ММ.ГГГГ."
        ),
        "btn_today": "Сегодня",
        "btn_tomorrow": "Завтра",
        # {hours} — все доступные промежутки выбранного дня
        "ask_time": (
            "На какое время?\n\n"
            "Выберите время из списка ниже или напишите своё в формате ЧЧ:ММ.\n"
            "Мы принимаем брони: {hours}."
        ),
        # --- date / time validation ---
        "date_bad": (
            "Не получилось распознать дату. Напишите её в формате ДД.ММ.ГГГГ — "
            "например, 15.08.2026."
        ),
        "date_past": "Эта дата уже прошла. Пожалуйста, выберите другую.",
        "time_bad": (
            "Не получилось распознать время. Напишите его в формате ЧЧ:ММ — "
            "например, 19:30."
        ),
        # --- unavailability (editable in the admin panel) ---
        "date_closed": (
            "К сожалению, на {date} бронирование недоступно. "
            "Пожалуйста, выберите другую дату."
        ),
        "time_closed": (
            "К сожалению, на это время бронь недоступна. "
            "Мы принимаем брони: {hours} — пожалуйста, выберите другое время."
        ),
        "ask_guests": "Сколько будет гостей?",
        "btn_guests_more": "Больше 8",
        "ask_guests_number": "Напишите число гостей:",
        "ask_name": "На чьё имя оформить бронь?",
        "ask_phone": (
            "Оставьте номер телефона — на случай, если нужно будет с вами связаться."
        ),
        "btn_share_contact": "📱 Поделиться контактом",
        "ask_requests": (
            "Есть особые пожелания?\n"
            "Если нет — нажмите «Пропустить»."
        ),
        "btn_skip": "Пропустить",
        "confirm_card": (
            "Проверьте, всё ли верно:\n\n"
            "📅 Дата: <b>{date}</b>\n"
            "🕐 Время: <b>{time}</b>\n"
            "👥 Гостей: <b>{guests}</b>\n"
            "👤 Имя: <b>{name}</b>\n"
            "📱 Телефон: <b>{phone}</b>\n"
            "💬 Пожелания: {requests}\n\n"
            "⏱ Обратите внимание: стол резервируется на 2,5 часа.\n\n"
            "Отправляем заявку?"
        ),
        "requests_none": "—",
        "btn_send": "✅ Отправить",
        "btn_edit": "✏️ Изменить",
        "btn_cancel": "❌ Отмена",
        "sent": (
            "Спасибо! Заявка отправлена. Менеджер проверит наличие мест и вернётся "
            "к вам в ближайшее время. ⏳"
        ),
        "cancelled": "Заявка отменена. Будем рады помочь, когда будете готовы.",
        "bookings_closed": (
            "🙁 Извините, приём броней временно приостановлен. "
            "Пожалуйста, свяжитесь с нами по телефону или загляните немного позже."
        ),
        # --- manager replies to client ---
        "client_confirmed": (
            "✅ Ваша бронь подтверждена!\n\n"
            "📅 <b>{date}</b> в <b>{time}</b>, {guests} гост(я/ей)\n"
            "⏱ Столик зарезервирован на 2,5 часа.\n"
            f"Ждём вас в <b>{RESTAURANT_NAME}</b>. Если планы изменятся — просто "
            "напишите нам."
        ),
        "client_alt": (
            "На <b>{date}</b> в <b>{time}</b> к сожалению всё занято. "
            "Можем предложить <b>{alt_time}</b> — подойдёт?"
        ),
        "btn_alt_ok": "✅ Подходит",
        "btn_alt_other": "🕐 Другое время",
        "client_declined": (
            "К сожалению, на выбранное время свободных столов нет. Будем рады видеть "
            "вас в другой день — напишите нам в любое время."
        ),
        "client_alt_accepted": (
            "Отлично, ждём вас! Бронь на новое время подтверждена. Если планы "
            "изменятся — просто напишите нам."
        ),
        "client_alt_declined": (
            "Понятно. Если захотите выбрать другое время — нажмите «Забронировать "
            "стол» в меню, и мы всё оформим."
        ),
        # --- menu ---
        "menu_text": "Наше меню 👇",
        "menu_no_link": (
            "Меню скоро появится здесь. А пока будем рады рассказать обо всём при "
            "бронировании."
        ),
        # --- events ---
        "events_header": f"🎭 <b>Ближайшие события в {RESTAURANT_NAME}</b>",
        "events_footer": "Хотите попасть на событие? Забронируйте стол 👇",
        "events_empty": "Пока анонсов нет — следите за обновлениями.",
        # --- hours & location ---
        "hours_text": (
            f"📍 <b>{RESTAURANT_NAME}</b>\n"
            "{address}\n"
            "🕐 {working_hours}\n"
            "☎️ {phone}\n"
            '<a href="{map_link}">Проложить маршрут</a>'
        ),
        # --- faq ---
        "faq_header": "Выберите вопрос:",
        "faq_empty": "Вопросы скоро появятся здесь.",
        "faq_back": "⬅️ К вопросам",
        # (legacy FAQ label/answer keys kept for backwards compatibility; the live
        #  FAQ is now stored in the database and editable from the admin panel.)
        "faq_parking": "Парковка",
        "faq_kids": "Детское меню",
        "faq_pets": "Можно ли с животными",
        "faq_dresscode": "Дресс-код",
        "faq_terrace": "Терраса",
        "faq_a_parking": "🅿️ (текст про парковку — заполнить)",
        "faq_a_kids": "🧒 (текст про детское меню — заполнить)",
        "faq_a_pets": "🐾 (текст про животных — заполнить)",
        "faq_a_dresscode": "👗 (текст про дресс-код — заполнить)",
        "faq_a_terrace": "🌿 (текст про террасу — заполнить)",
        # --- misc ---
        "back_to_menu": "⬅️ В меню",
        "unknown": "Не совсем понял. Выберите пункт в меню ниже 👇",
    },
    "en": {
        "choose_language": (
            f"🇷🇺 Добро пожаловать в <b>{RESTAURANT_NAME}</b>\n"
            f"🇬🇧 Welcome to <b>{RESTAURANT_NAME}</b>\n\n"
            "Выберите язык / Choose your language"
        ),
        "main_menu": (
            f"Glad to see you at <b>{RESTAURANT_NAME}</b>\n"
            "How can we help?"
        ),
        "btn_book": "📅 Book a table",
        "btn_menu": "📖 Menu",
        "btn_events": "🎭 Events",
        "btn_hours": "📍 Hours & location",
        "btn_faq": "❓ FAQ",
        "btn_language": "🌐 Язык / Language",
        "ask_date": (
            "What date would you like to book?\n\n"
            "Tap \"Today\" or \"Tomorrow\", or type your own date "
            "as DD.MM.YYYY."
        ),
        "btn_today": "Today",
        "btn_tomorrow": "Tomorrow",
        # {hours} — every bookable window of the chosen day
        "ask_time": (
            "What time?\n\n"
            "Pick a time below or type your own as HH:MM.\n"
            "We take bookings: {hours}."
        ),
        "date_bad": (
            "I couldn't read that date. Please type it as DD.MM.YYYY — "
            "for example, 15.08.2026."
        ),
        "date_past": "That date has already passed. Please choose another one.",
        "time_bad": (
            "I couldn't read that time. Please type it as HH:MM — "
            "for example, 19:30."
        ),
        "date_closed": (
            "Unfortunately we're not taking bookings for {date}. "
            "Please choose another date."
        ),
        "time_closed": (
            "Unfortunately that time isn't available. "
            "We take bookings: {hours} — please pick another time."
        ),
        "ask_guests": "How many guests?",
        "btn_guests_more": "More than 8",
        "ask_guests_number": "Please type the number of guests:",
        "ask_name": "What name should we put the reservation under?",
        "ask_phone": "Please share a phone number in case we need to reach you.",
        "btn_share_contact": "📱 Share contact",
        "ask_requests": (
            "Any special requests?\n"
            'If none, tap "Skip".'
        ),
        "btn_skip": "Skip",
        "confirm_card": (
            "Please check everything is correct:\n\n"
            "📅 Date: <b>{date}</b>\n"
            "🕐 Time: <b>{time}</b>\n"
            "👥 Guests: <b>{guests}</b>\n"
            "👤 Name: <b>{name}</b>\n"
            "📱 Phone: <b>{phone}</b>\n"
            "💬 Requests: {requests}\n\n"
            "⏱ Please note: the table is reserved for 2.5 hours.\n\n"
            "Send the request?"
        ),
        "requests_none": "—",
        "btn_send": "✅ Send",
        "btn_edit": "✏️ Edit",
        "btn_cancel": "❌ Cancel",
        "sent": (
            "Thank you! Your request has been sent. Our manager will check "
            "availability and get back to you shortly. ⏳"
        ),
        "cancelled": "Request cancelled. We'll be happy to help whenever you're ready.",
        "bookings_closed": (
            "🙁 Sorry, we're not taking bookings at the moment. "
            "Please call us or check back a little later."
        ),
        "client_confirmed": (
            "✅ Your reservation is confirmed!\n\n"
            "📅 <b>{date}</b> at <b>{time}</b>, {guests} guest(s)\n"
            "⏱ The table is reserved for 2.5 hours.\n"
            f"We look forward to seeing you at <b>{RESTAURANT_NAME}</b>. "
            "If your plans change, just let us know."
        ),
        "client_alt": (
            "Unfortunately we're fully booked for <b>{date}</b> at <b>{time}</b>. "
            "We could offer <b>{alt_time}</b> — does that work?"
        ),
        "btn_alt_ok": "✅ Works for me",
        "btn_alt_other": "🕐 Another time",
        "client_declined": (
            "Unfortunately there are no tables available for that time. We'd be happy "
            "to welcome you another day — reach out anytime."
        ),
        "client_alt_accepted": (
            "Great, see you then! Your reservation for the new time is confirmed. "
            "If your plans change, just let us know."
        ),
        "client_alt_declined": (
            "No problem. If you'd like to pick another time, tap \"Book a table\" in "
            "the menu and we'll sort it out."
        ),
        "menu_text": "Our menu 👇",
        "menu_no_link": (
            "The menu will appear here soon. In the meantime we'll be glad to tell "
            "you everything when you book."
        ),
        "events_header": f"🎭 <b>Upcoming events at {RESTAURANT_NAME}</b>",
        "events_footer": "Want to join? Book a table 👇",
        "events_empty": "No events announced yet — stay tuned.",
        "hours_text": (
            f"📍 <b>{RESTAURANT_NAME}</b>\n"
            "{address}\n"
            "🕐 {working_hours}\n"
            "☎️ {phone}\n"
            '<a href="{map_link}">Get directions</a>'
        ),
        "faq_header": "Choose a question:",
        "faq_empty": "FAQ will appear here soon.",
        "faq_back": "⬅️ Back to questions",
        "faq_parking": "Parking",
        "faq_kids": "Kids' menu",
        "faq_pets": "Pets allowed?",
        "faq_dresscode": "Dress code",
        "faq_terrace": "Terrace",
        "faq_a_parking": "🅿️ (parking info — to be filled in)",
        "faq_a_kids": "🧒 (kids' menu info — to be filled in)",
        "faq_a_pets": "🐾 (pets info — to be filled in)",
        "faq_a_dresscode": "👗 (dress code info — to be filled in)",
        "faq_a_terrace": "🌿 (terrace info — to be filled in)",
        "back_to_menu": "⬅️ Menu",
        "unknown": "I didn't quite get that. Please pick an option below 👇",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Return a localized string, formatted with kwargs. Falls back to Russian."""
    lang = lang if lang in T else "ru"
    template = T[lang].get(key) or T["ru"].get(key, key)
    return template.format(**kwargs) if kwargs else template
