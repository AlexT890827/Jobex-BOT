import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot działa!"

def run():
    app_flask.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# TOKEN i Google Sheets konfiguracja
TOKEN = '7799950814:AAFbnyKM6qLOaJWNkgKBXysaEXTjsmRJtIc'
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = 'credentials.json'
SPREADSHEET_ID = '1fI0z9PJfvqs_oQsgw1KQRCeWpuROnOt6rim1i991UCY'
SHEET_KANDYDA = 'Kandydaci'
SHEET_OFERTE = 'Oferty'

# Google Sheets inicjalizacja
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)
worksheet_candidates = spreadsheet.worksheet(SHEET_KANDYDA)
worksheet_offers = spreadsheet.worksheet(SHEET_OFERTE)

# Stany rozmowy
NAME, PHONE, AGE, GENDER, LOCATION, ARRIVAL_TIME, CITY, RELOCATION = range(8)

logging.basicConfig(level=logging.INFO)

age_keyboard = [[InlineKeyboardButton("18-40", callback_data='age_18-40'),
                 InlineKeyboardButton("40-50", callback_data='age_40-50'),
                 InlineKeyboardButton("50-60", callback_data='age_50-60')]]

gender_keyboard = [[InlineKeyboardButton("Жінка", callback_data='gender_Жінка'),
                    InlineKeyboardButton("Чоловік", callback_data='gender_Чоловік'),
                    InlineKeyboardButton("Сімейна пара", callback_data='gender_пара')]]

location_keyboard = [[InlineKeyboardButton("В Польщі", callback_data='location_В Польщі'),
                      InlineKeyboardButton("Лише планую приїхати", callback_data='location_Лише планую приїхати')]]

arrival_time_keyboard = [[InlineKeyboardButton("Якнайшвидше", callback_data='arrival_якнайшвидше'),
                          InlineKeyboardButton("через тиждень", callback_data='arrival_тиждень'),
                          InlineKeyboardButton("на наступний місяць", callback_data='arrival_місяць')]]

relocation_keyboard = [[InlineKeyboardButton("ТАК", callback_data='relocation_TAK'),
                         InlineKeyboardButton("НІ", callback_data='relocation_NІ')]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Мене звати JOBEX, я твій особистий рекрутер, допоможу тобі знайти найкращу роботу в Польщі!")
    await update.message.reply_text("Давай знайомитись!")
    await update.message.reply_text("Як тебе звати?")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data['name'] = name
    contact_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Поділитись номером телефону", request_contact=True)]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(f"{name}, поділись зі мною номером телефону, щоб бути на зв'язку зі мною:", reply_markup=contact_keyboard)
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.contact.phone_number if update.message.contact else update.message.text
    await update.message.reply_text("Скільки тобі років?", reply_markup=InlineKeyboardMarkup(age_keyboard))
    return AGE

async def process_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('age_'):
        age = data.split('_')[1]
        context.user_data['age'] = age
        await query.message.reply_text(f"Твій вік: {age}")
        await query.message.reply_text("Для кого ти шукаєш роботу?", reply_markup=InlineKeyboardMarkup(gender_keyboard))
        return GENDER

    elif data.startswith('gender_'):
        gender = data.split('_')[1]
        context.user_data['gender'] = gender
        await query.message.reply_text(f"Стать: {gender}")
        await query.message.reply_text("Де ти зараз знаходишся?", reply_markup=InlineKeyboardMarkup(location_keyboard))
        return LOCATION

    elif data.startswith('location_'):
        location = data.replace('location_', '')
        context.user_data['location'] = location
        await query.message.reply_text(f"Локація: {location}")
        if location == 'В Польщі':
            await query.message.reply_text("В якому місті ти зараз проживаєш?")
            return CITY
        else:
            await query.message.reply_text("Коли ти плануєш приїхати?", reply_markup=InlineKeyboardMarkup(arrival_time_keyboard))
            return ARRIVAL_TIME

    elif data.startswith('arrival_'):
        arrival = data.split('_')[1]
        context.user_data['arrival_time'] = arrival
        await query.message.reply_text(f"Час приїзду: {arrival}")
        if arrival == 'місяць':
            await query.message.reply_text("Звʼяжемось пізніше щодо актуальних вакансій.")
            await save_candidate(update, context)
            return ConversationHandler.END
        else:
            await query.message.reply_text("В якому місті ти плануєш жити?")
            return CITY

    elif data.startswith('relocation_'):
        relocation = 'ТАК' if data.endswith('TAK') else 'НІ'
        context.user_data['relocation'] = relocation
        await query.message.reply_text(f"Готовність до переїзду: {relocation}")
        await save_candidate(update, context)
        await query.message.reply_text("Дякую! Підбираю вакансії...")
        await send_matching_offers(update, context)
        return ConversationHandler.END

async def get_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['city'] = update.message.text.strip().title()
    await update.message.reply_text("Чи готові ви на переїзд?", reply_markup=InlineKeyboardMarkup(relocation_keyboard))
    return RELOCATION

from datetime import datetime
from zoneinfo import ZoneInfo  # python 3.9+

async def save_candidate(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    now = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M:%S")

    row = [now, data.get("name"), data.get("age"), data.get("phone"), data.get("gender"),
           data.get("location"), data.get("city", ""), data.get("relocation", ""), "Новий", ""]
    worksheet_candidates.append_row(row)

async def send_matching_offers(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update_or_query.effective_chat.id

    user_city = context.user_data.get('city', '').lower()
    willing_to_relocate = context.user_data.get('relocation', '').upper() == 'ТАК'
    user_age = context.user_data.get('age', '')
    user_gender = context.user_data.get('gender', '').lower()

    # Fetch all records first
    offers = worksheet_offers.get_all_records()

    # Now filter if you need to based on a condition
    filtered_offers = [offer for offer in offers if offer.get('Status') == 'Актуально']

    def age_in_range(age_text, user_age):
        if not age_text or not user_age:
            return True
        try:
            c_min, c_max = map(int, age_text.split('-'))
            return c_min <= int(user_age) <= c_max
        except:
            return True

    matching_offers = [
        offer for offer in offers
        if (offer.get('Місто', '').lower() == user_city or willing_to_relocate)
        and (offer.get('Стать', '').strip().lower() in [user_gender, 'всі', ''])
        and age_in_range(offer.get('Вік', ''), user_age)
        and (offer.get('Статус') == 'Актуально')
    ]

    context.user_data['matching_offers'] = matching_offers[:10]

    if matching_offers:
        await context.bot.send_message(chat_id=chat_id, text="🔎 Ось декілька вакансій для тебе:")
        for idx, offer in enumerate(matching_offers[:10]):
            text = f"📌 *{offer.get('Назва')}*\n{offer.get('Опис')}\nМісто: {offer.get('Місто')}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Цікавить", callback_data=f"interested_{idx}")]]
            )
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=chat_id, text="Наразі немає відповідних вакансій.")

async def handle_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offer_index = int(query.data.replace("interested_", ""))
    selected_offer = context.user_data.get("matching_offers", [])[offer_index]
    offer_name = selected_offer.get('Назва', 'Без назви')
    try:
        phone = context.user_data.get("phone")
        cell = worksheet_candidates.find(phone)
        if cell:
            worksheet_candidates.update_cell(cell.row, 10, f"Цікавить: {offer_name}")
    except Exception as e:
        logging.error(f"Помилка оновлення інтересу: {e}")
    await query.message.reply_text(f"✅ Збережено! Тебе цікавить: {offer_name}")
    await query.message.reply_text("Щоб отримати більш детальну інформацію зателефонуй до мене за номером 📞  +48 666 740 852.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Розмова завершена.', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), get_phone)],
            AGE: [CallbackQueryHandler(process_callback, pattern='^age_')],
            GENDER: [CallbackQueryHandler(process_callback, pattern='^gender_')],
            LOCATION: [CallbackQueryHandler(process_callback, pattern='^location_')],
            ARRIVAL_TIME: [CallbackQueryHandler(process_callback, pattern='^arrival_')],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            RELOCATION: [CallbackQueryHandler(process_callback, pattern='^relocation_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_interest, pattern='^interested_'))

    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
 keep_alive()
 main()

