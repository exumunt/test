import asyncio
import os
import aiohttp
import json
import tempfile
import ssl
import time
import random
from rubpy import BotClient
from rubpy.bot.filters import commands, text
from rubpy.bot.models import Keypad, KeypadRow, Button
from rubpy.bot.enums import ChatKeypadTypeEnum, ButtonTypeEnum
from googletrans import Translator

# توکن‌های شما
BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")
TMDB_ACCOUNT_ID = os.getenv("TMDB_ACCOUNT_ID")

# ساخت یک شیء از کتابخانه‌های مورد نیاز
translator = Translator()

# سیستم کش: اطلاعات و زمان انقضا
cache = {
    "popular_movies": {"data": None, "expires": 0},
    "now_playing": {"data": None, "expires": 0},
    "top_rated_tv": {"data": None, "expires": 0},
    "popular_anime": {"data": None, "expires": 0},
    "popular_cartoons": {"data": None, "expires": 0}
}
CACHE_EXPIRY_SECONDS = 24 * 60 * 60

# ساخت منوی اصلی
main_menu = Keypad(
    rows=[
        KeypadRow(buttons=[Button(id="top_movies", type=ButtonTypeEnum.SIMPLE, button_text="برترین فیلم و سریال ها 📽")]),
        KeypadRow(buttons=[Button(id="top_anime", type=ButtonTypeEnum.SIMPLE, button_text="انیمه تاپ 💯"), Button(id="cartoons", type=ButtonTypeEnum.SIMPLE, button_text="کارتون - 🔞")]),
        KeypadRow(buttons=[Button(id="select_genre", type=ButtonTypeEnum.SIMPLE, button_text="انتخواب ژانر برای تماشا 🎭")]),
        KeypadRow(buttons=[Button(id="profile", type=ButtonTypeEnum.SIMPLE, button_text="👤 پروفایل"), Button(id="daily_suggestion", type=ButtonTypeEnum.SIMPLE, button_text="پیشنهاد امروز ⁉️")])
    ],
    resize_keyboard=True
)

# ساخت کیبورد برای زیرمنوی فیلم و سریال
movies_series_menu = Keypad(
    rows=[
        KeypadRow(buttons=[Button(id="new_movies", type=ButtonTypeEnum.SIMPLE, button_text="جدیدترین فیلم ها 🎬")]),
        KeypadRow(buttons=[Button(id="new_series_episodes", type=ButtonTypeEnum.SIMPLE, button_text="قسمت جدید سریال ها 📺"), Button(id="top_series", type=ButtonTypeEnum.SIMPLE, button_text="برترین سریال ها 🔝")]),
        KeypadRow(buttons=[Button(id="hottest_movies", type=ButtonTypeEnum.SIMPLE, button_text="خفن ترین فیلم ها 😎")]),
        KeypadRow(buttons=[Button(id="back_to_main", type=ButtonTypeEnum.SIMPLE, button_text="بازگشت به منوی اصلی 🔙")])
    ], resize_keyboard=True
)

async def fetch_data_with_cache(session, url, cache_key):
    current_time = time.time()
    if cache_key in cache and cache[cache_key]["data"] and current_time < cache[cache_key]["expires"]:
        print(f"Data for {cache_key} retrieved from cache.")
        return cache[cache_key]["data"]

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"
    }
    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)

            cache[cache_key]["data"] = data.get('results', [])
            cache[cache_key]["expires"] = current_time + CACHE_EXPIRY_SECONDS
            print(f"Data for {cache_key} fetched from API and cached.")

            return data.get('results', [])
    except aiohttp.ClientError as e:
        print(f"Error fetching data for {cache_key}: {e}")
        return None

async def get_movie_details(session, movie_id, is_tv=False):
    kind = "tv" if is_tv else "movie"
    url = f"https://api.themoviedb.org/3/{kind}/{movie_id}"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"
    }
    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            info = await response.json(content_type=None)

            genres = ", ".join([genre['name'] for genre in info.get('genres', [])])
            translated_genres = translator.translate(genres, dest='fa').text

            plot = info.get('overview', "خلاصه در دسترس نیست.")
            translated_plot = translator.translate(plot, dest='fa').text

            title_key = 'name' if is_tv else 'title'
            year_key = 'first_air_date' if is_tv else 'release_date'

            return {
                "title": info.get(title_key, 'N/A'),
                "year": info.get(year_key, 'N/A')[:4],
                "genres": translated_genres,
                "plot": translated_plot,
                "rating": round(info.get('vote_average', 0), 1),
                "poster_path": info.get('poster_path', None),
                "kind": kind
            }
    except aiohttp.ClientError as e:
        print(f"Error fetching {kind} details from TMDB: {e}")
        return None

async def send_media_message(client, update, media_info, session):
    if not media_info or not media_info['poster_path']:
        await update.reply("پوستر برای این عنوان در دسترس نیست.")
        return

    # آدرس واسط برای حل مشکل فیلترینگ تصاویر
    poster_url = f"https://images.weserv.nl/?url=https://image.tmdb.org/t/p/original{media_info['poster_path']}"
    temp_file_path = f"{tempfile.gettempdir()}/{media_info['title'].replace(' ', '_')}.jpg"

    try:
        async with session.get(poster_url) as poster_response:
            poster_response.raise_for_status()
            poster_data = await poster_response.read()

        with open(temp_file_path, "wb") as f:
            f.write(poster_data)

        message_text = f"🎥 **{media_info['title']}**\n"
        message_text += f"ژانر : {media_info['genres']}\n"
        message_text += f"سال ساخت : {media_info['year']}\n\n"
        message_text += f"⭐️ IMDB : {media_info['rating']}/10\n\n"
        message_text += f"• {media_info['plot']}"

        await client.send_file(
            chat_id=update.chat_id,
            file=temp_file_path,
            file_name=os.path.basename(temp_file_path),
            text=message_text,
            type="Image",
            reply_to_message_id=update.new_message.message_id
        )
    except aiohttp.ClientResponseError as e:
        if e.status == 404:
            print(f"Poster not found for {media_info['title']}.")
            await update.reply("پوستر برای این عنوان پیدا نشد.")
        else:
            print(f"Error fetching poster from TMDB: {e}")
            await update.reply("متاسفم، مشکلی در دانلود پوستر پیش آمد.")
    except aiohttp.ClientError as e:
        print(f"Error downloading poster: {e}")
        await update.reply("متاسفم، مشکلی در دانلود پوستر پیش آمد.")
    except Exception as e:
        print(f"Error sending file: {e}")
        await update.reply("متاسفم، مشکلی در ارسال فایل پیش آمد.")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

async def main():
    bot = BotClient(BOT_TOKEN, use_webhook=True)

    ssl_context = ssl.create_default_context()
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:

        @bot.on_update(commands("start"))
        async def start_handler(client, update):
            try:
                if update.new_message:
                    await update.reply(
                        "به ربات فیلم و سریال خوش آمدید. لطفا از منوی زیر یکی را انتخاب کنید:",
                        chat_keypad=main_menu,
                        chat_keypad_type=ChatKeypadTypeEnum.NEW
                    )
            except Exception as e:
                print(f"Error in start handler: {e}")

        @bot.on_update(text("برترین فیلم و سریال ها 📽"))
        async def top_movies_handler(client, update):
            try:
                await update.reply(
                    "⭕️ جستجو در لیست بهترین های روز ... ",
                    chat_keypad=movies_series_menu,
                    chat_keypad_type=ChatKeypadTypeEnum.NEW
                )
            except Exception as e:
                print(f"Error in top movies handler: {e}")

        @bot.on_update(text("بازگشت به منوی اصلی 🔙"))
        async def back_to_main_handler(client, update):
            try:
                await update.reply(
                    "به منوی اصلی بازگشتید.",
                    chat_keypad=main_menu,
                    chat_keypad_type=ChatKeypadTypeEnum.NEW
                )
            except Exception as e:
                print(f"Error in back to main handler: {e}")

        @bot.on_update(text("جدیدترین فیلم ها 🎬"))
        async def latest_movies_handler(client, update):
            try:
                await update.reply("⭕️ در حال جستجو برای جدیدترین فیلم ها ...")
                movies_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/movie/now_playing", "now_playing")
                if movies_list:
                    random_movies = random.sample(movies_list, min(5, len(movies_list)))
                    for movie_data in random_movies:
                        movie_info = await get_movie_details(session, movie_data['id'])
                        await send_media_message(client, update, movie_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم لیست فیلم‌ها را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in latest movies handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        @bot.on_update(text("قسمت جدید سریال ها 📺"))
        async def latest_series_episodes_handler(client, update):
            try:
                await update.reply("⭕️ در حال آماده‌سازی قسمت های جدید سریال ها ...")
            except Exception as e:
                print(f"Error in latest series handler: {e}")

        @bot.on_update(text("برترین سریال ها 🔝"))
        async def top_series_handler(client, update):
            try:
                await update.reply("⭕️ در حال جستجو برای برترین سریال ها ...")
                series_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/tv/top_rated", "top_rated_tv")
                if series_list:
                    random_series = random.sample(series_list, min(5, len(series_list)))
                    for series_data in random_series:
                        series_info = await get_movie_details(session, series_data['id'], is_tv=True)
                        await send_media_message(client, update, series_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم لیست سریال‌ها را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in top series handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        @bot.on_update(text("خفن ترین فیلم ها 😎"))
        async def hottest_movies_handler(client, update):
            try:
                await update.reply("⭕️ در حال جستجو برای خفن‌ترین فیلم ها ...")
                movies_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/movie/popular", "popular_movies")
                if movies_list:
                    random_movies = random.sample(movies_list, min(5, len(movies_list)))
                    for movie_data in random_movies:
                        movie_info = await get_movie_details(session, movie_data['id'])
                        await send_media_message(client, update, movie_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم لیست فیلم‌ها را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in hottest movies handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        @bot.on_update(text("انیمه تاپ 💯"))
        async def top_anime_handler(client, update):
            try:
                await update.reply("⭕️ در حال جستجو برای انیمه ها ...")
                anime_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/discover/movie?with_genres=16&sort_by=vote_count.desc", "popular_anime")
                if anime_list:
                    random_anime = random.sample(anime_list, min(5, len(anime_list)))
                    for anime_data in random_anime:
                        anime_info = await get_movie_details(session, anime_data['id'])
                        await send_media_message(client, update, anime_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم لیست انیمه‌ها را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in top anime handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        @bot.on_update(text("کارتون - 🔞"))
        async def cartoons_handler(client, update):
            try:
                await update.reply("⭕️ در حال جستجو برای کارتون ها ...")
                cartoons_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/discover/movie?with_genres=16,10751&sort_by=vote_count.desc", "popular_cartoons")
                if cartoons_list:
                    random_cartoons = random.sample(cartoons_list, min(5, len(cartoons_list)))
                    for cartoon_data in random_cartoons:
                        cartoon_info = await get_movie_details(session, cartoon_data['id'])
                        await send_media_message(client, update, cartoon_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم لیست کارتون‌ها را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in cartoons handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        @bot.on_update(text("انتخواب ژانر برای تماشا 🎭"))
        async def select_genre_handler(client, update):
            try:
                await update.reply("⭕️ در حال آماده‌سازی ژانرها ...")
            except Exception as e:
                print(f"Error in select genre handler: {e}")

        @bot.on_update(text("👤 پروفایل"))
        async def profile_handler(client, update):
            try:
                await update.reply("در حال آماده‌سازی پروفایل ...")
            except Exception as e:
                print(f"Error in profile handler: {e}")

        @bot.on_update(text("پیشنهاد امروز ⁉️"))
        async def daily_suggestion_handler(client, update):
            try:
                await update.reply("⭕️ در حال دریافت پیشنهاد امروز...")
                movies_list = await fetch_data_with_cache(session, "https://api.themoviedb.org/3/movie/popular", "popular_movies")
                if movies_list:
                    random_movies = random.sample(movies_list, min(5, len(movies_list)))
                    for movie_data in random_movies:
                        movie_info = await get_movie_details(session, movie_data['id'])
                        await send_media_message(client, update, movie_info, session)
                else:
                    await update.reply("متاسفم، در حال حاضر نمی‌توانم فیلم‌های پیشنهادی را دریافت کنم. لطفا بعدا دوباره امتحان کنید.")
            except Exception as e:
                print(f"Error in daily suggestion handler: {e}")
                await update.reply("متاسفم، مشکلی پیش آمد. لطفا بعدا دوباره امتحان کنید.")

        while True:
            try:
                await bot.run(path="/", host="0.0.0.0", port=os.getenv("PORT", 8080))
            except Exception as e:
                print(f"An error occurred in bot.run: {e}. Restarting in 5 seconds...")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
