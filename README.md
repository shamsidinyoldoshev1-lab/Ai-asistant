# Telegram Shaxsiy AI Agent (Userbot + Boshqaruv boti)

Ushbu loyiha sizning shaxsiy Telegram akkauntingiz orqali xabarlarni qabul qiluvchi, o'chirilgan xabarlarni saqlovchi va Claude AI orqali yozishmalarga sizning uslubingizda javob beruvchi shaxsiy AI agent hisoblanadi.

---

## 📁 Loyiha tuzilishi

```text
├── main.py              # Loyihani ishga tushirish nuqtasi (asyncio loop)
├── config.py            # Sozlamalar va logging boshqaruvi
├── db.py                # SQLite (aiosqlite) bilan ishlash moduli
├── userbot.py           # Telethon yordamida userbot (kiruvchi/o'chirilgan/tahrirlangan xabarlar)
├── control_bot.py       # aiogram 3 boshqaruv boti (adminga xabarnoma va boshqaruv)
├── cleanup.py           # 30 kundan eski ma'lumotlarni avtomatik tozalash
├── requirements.txt     # Kerakli Python kutubxonalari
├── .env.example         # Konfiguratsiya namunasi
├── .gitignore           # Maxfiy va keraksiz fayllar filtri
└── README.md            # Qo'llanma
```

---

## 🚀 1-BOSQICH: Sozlash va tayyorgarlik

1-bosqichda loyiha tuzilishi yaratildi, SQLite ma'lumotlar bazasi ulandi va Userbot barcha kiruvchi hamda chiquvchi xabarlarni (matn va media fayllarini `saved_media/` papkasiga) SQLite bazasiga saqlaydigan holatga keltirildi.

### 1. `.env` faylini sozlash

`.env.example` faylidan nusxa olib, `.env` nomli yangi fayl yarating:
```powershell
Copy-Item .env.example .env
```

`.env` faylini ochib, quyidagi ma'lumotlarni kiriting:
1. `TELEGRAM_API_ID` va `TELEGRAM_API_HASH`:
   - [my.telegram.org](https://my.telegram.org) saytiga shaxsiy telefon raqamingiz orqali kiring.
   - **API development tools** bo'limiga o'ting.
   - Ilova yarating va berilgan `api_id` hamda `api_hash` ni ko'chirib oling.
2. `TELEGRAM_BOT_TOKEN`:
   - Telegramda [@BotFather](https://t.me/BotFather) ga `/newbot` buyrug'ini yuboring va token oling.
3. `ADMIN_USER_ID`:
   - [@userinfobot](https://t.me/userinfobot) orqali o'zingizning Telegram ID raqamingizni aniqlab yozing.
4. `ANTHROPIC_API_KEY`:
   - Anthropic konsolidan olingan Claude API kaliti (4-bosqich uchun).

---

## 🗑 2-BOSQICH: O'chirilgan xabarlarni saqlash va yuborish

2-bosqichda quyidagi imkoniyatlar qo'shildi:
1. **O'chirilgan xabarlarni tutish (`events.MessageDeleted`):**
   - Agar suhbatdosh yuborgan xabarini (matn yoki media) o'chirib tashlasa, Userbot buni darhol aniqlaydi.
   - Bazadan o'sha xabar topiladi, `is_deleted = 1` qilib belgilanadi.
   - Boshqaruv boti orqali sizga (faqat sizning `ADMIN_USER_ID` ingizga):
     - Kim o'chirgani (ismi, username, ID)
     - Qaysi chatda yozilgani
     - Qachon yozilgani va qachon o'chirilgani
     - Asl xabar matni
     - Agar rasm, ovozli xabar yoki fayl bo'lsa — o'sha fayl bilan birga xabarnoma yuboriladi!
2. **Tahrirlangan xabarlarni saqlash (`events.MessageEdited`):**
   - Suhbatdosh xabarini o'zgartirsa, bazada `original_text` (birinchi yozilgan holati) va yangi `text` saqlanib boradi.
3. **Avtomatik tozalash (`cleanup.py`):**
   - 30 kundan eski bo'lgan xabarlar bazadan va `saved_media/` papkasidan orqa fonda (har 24 soatda) avtomatik tozalanadi (muddat `.env` orqali sozlanadi).

---

## 🤖 3-BOSQICH: Boshqaruv boti va tasdiq tugmalari

3-bosqichda aiogram 3 asosida to'liq boshqaruv interfeysi yaratildi:

1. **Javob qoralamalari va tasdiqlash tugmalari:**
   - Har bir javob taklifi adminga quyidagi tugmalar bilan yuboriladi:
     - `[✅ Yuborish]` — Bosilganda xabar Userbot orqali suhbatdoshga jo'natiladi va qoralama yuborilgan deb belgilanadi.
     - `[✏️ Tahrirlash]` — FSM (Finite State Machine) orqali matnni tahrirlash holati yoqiladi. Admin yangi matn kiritgach, qoralama yangilanadi va yana tasdiq so'raladi.
     - `[❌ Bekor qilish]` — Qoralama bekor qilinadi va hech narsa yuborilmaydi.
2. **Boshqaruv buyruqlari:**
   - `/holat` — Agent holati (Faol / Pauzada), yozishmalar statistikasi va maxsus sozlangan kontaktlar ro'yxati.
   - `/pauza` — Agentni to'xtatish (yangi javoblar va tasdiq so'rovlari vaqtincha kelmaydi).
   - `/davom` — Agent faoliyatini qayta tiklash.
   - `/rejim <kontakt> <tasdiq|avto|aralash|ochiq>` — Muayyan kontakt uchun javob berish rejimini belgilash:
     - `tasdiq`: Har bir xabarga qoralama tayyorlab tasdiq so'raydi (standart rejim).
     - `avto`: Agent o'zi mustaqil javob qaytaradi.
     - `aralash`: Oddiy savollarga o'zi, muhimlariga tasdiq so'raydi.
     - `ochiq`: Agent bu kontaktga umuman javob qaytarmaydi.
   - `/yoz <kontakt> <matn>` — Muayyan kontaktga agent orqali tasdiqlash uchun xabar qoralamasini chiqarish.
   - `/test_qoralama` — Tasdiq tugmalari va tahrirlash mexanizmini to'g'ridan-to'g'ri sinab ko'rish.
   - `/cancel` — Har qanday faol FSM amaliyotini (masalan tahrirlashni) bekor qilish.

---

## 🧠 4-BOSQICH: Claude bilan javob tayyorlash (uslub, kontekst)

4-bosqichda shaxsiy yozish uslubingizni o'rganuvchi va Claude API orqali javob taklif qiluvchi intellektual yadro yaratildi:

1. **Shaxsiy yozish uslubi va Few-Shot namunalar (`style_samples.json`):**
   - 3 ta tilda (o'zbek, rus, ingliz) va 3 ta ohang toifasida tabiiy yozishmalardan iborat namunalar bazasi kiritildi.
   - Claude javob yozishda aynan shu namunalardagi insoniy, qisqa va tabiiy ohangga taqlid qiladi.
   - **O'z yozishmalaringizni yuklash:** Telegram Desktop da chatlar tarixini JSON formatida eksport qilib (`result.json`), `ai.import_telegram_export("result.json", "Ismingiz")` orqali 30-50 ta shaxsiy namunangizni tizimga qo'shishingiz mumkin.

2. **Muloqot ohangini boshqarish (`/ohang`):**
   - `oila` — Juda samimiy, erkin, do'stona va iliq munosabat.
   - `ish` — Rasmiy, ishchan, professional va lo'nda.
   - `notanish` — Qisqa, ehtiyotkor, shaxsiy ma'lumot bermaydigan.
   - Buyruq orqali sozlash: `/ohang @username oila` yoki `/ohang 12345678 ish`.

3. **20 ta xabar konteksti:**
   - Har bir suhbatdosh bilan oxirgi 20 ta xabar bazadan olinib, Claude'ga to'liq dialog konteksti sifatida uzatiladi.

4. **Avtomatik javob qoralamasi:**
   - Sizga yangi xabar kelganda (agar kontakt `tasdiq` rejimida bo'lsa), Claude darhol javob qoralamasini tayyorlaydi.
   - Boshqaruv botingizga quyidagi tugmalar bilan bildirishnoma keladi:
     `[✅ Yuborish] [✏️ Tahrirlash] [❌ Bekor qilish]`
   - `[✅ Yuborish]` ni bossangiz, xabar sizning shaxsiy Telegram akkauntingizdan suhbatdoshga ketadi!

5. **Guruhlar xavfsizligi:**
   - Guruhlarga kelgan begona xabarlarga agent aralashmaydi. Faqat sizning ismingiz tilga olinganda (@username yoki ism) yoki sizning xabaringizga javob (reply) berilgandagina javob tayyorlanadi.

---

## 🛡 5-BOSQICH: Rejimlar, xavfsizlik filtri, kechikishlar

5-bosqichda agentning to'liq xavfsizligi, akkauntni spam blokirovkasidan himoya qilish va kontaktlar bo'yicha moslashuvchan javob berish rejimlari joriy qilindi:

### 1. Javob berish rejimlari (Har bir kontakt uchun alohida)
- **`tasdiq`** (standart rejim): Yangi kontaktlar uchun standart holat. Agent javob qoralamasini tayyorlab, sizning boshqaruv botingizga yuboradi. Siz `[✅ Yuborish]`, `[✏️ Tahrirlash]` yoki `[❌ Bekor qilish]` tugmalarini bosmaguningizcha hech narsa yuborilmaydi.
- **`avto`**: Agent xabarga o'zi mustaqil va tabiiy javob beradi (adminga yuborilgan javob haqida bildirishnoma boradi). *Eslatma: Agar nozik mavzu aniqlansa, avto rejim bo'lsa ham avtomatik javob to'xtatiladi!*
- **`aralash`**: Oddiy savollarga (salomlashish, hol-ahvol, ish vaqti, manzil, lokatsiya) o'zi javob qaytaradi. Uchrashuv, kelishuv, va'da yoki shaxsiy masalalarda esa tasdiq so'raydi.
- **`ochiq`**: Agent ushbu kontaktga umuman javob qaytarmaydi (sukut saqlaydi).

Rejimni o'rnatish buyrug'i:
```text
/rejim @username avto
/rejim 12345678 aralash
/rejim @do'stim tasdiq
/rejim @boshqa_kontakt ochiq
```

---

### 2. Xavfsizlik filtri (`safety.py`)
Agent hech qachon nozik va xavfli mavzularda mustaqil javob bermaydi! Quyidagi toifalar qat'iy nazorat qilinadi:
- 💳 **Karta raqamlari:** 16 xonali karta raqamlari (Uzcard, Humo, Visa, Mastercard).
- 🔑 **Maxfiy kodlar va parollar:** SMS kodlar, tasdiqlash kodi, PIN, CVV, OTP.
- 💰 **Moliya:** Pul, to'lov, qarz, narx, hisob raqam, o'tkazma, kredit.
- 📜 **Shartnoma va va'dalar:** Bitim, kontrakt, imzo, kafolat, qat'iy va'da berish.
- 💊 **Tibbiyot:** Dori, tashxis, retsept, davolash, operatsiya.
- ⚖️ **Huquqiy masalalar:** Sud, prokuratura, advokat, ariza, qonun, jarima.

**Qanday ishlaydi?**
Agar suhbatdosh nozik mavzuda yozsa:
1. Agent zudlik bilan avto-javobni bekor qiladi.
2. Boshqaruv botingizga qizil ogohlantirish keladi (`🚨 XAVFSIZLIK FILTRI OGOHLANTIRISHI!`).
3. Kelgan xabar matni, toifasi va sababi ko'rsatiladi hamda ehtiyotkor qoralama taklif qilinadi.

---

### 3. Akkauntni spamdan himoyalash (Anti-Flood va insoniy imitatsiya)
Telegram sizning akkauntingizni bot yoki spamer deb hisoblamasligi uchun:
- **Tasodifiy kechikish:** Har bir xabar yuborishdan oldin **3-10 soniya** tasodifiy tanaffus qilinadi.
- **"Yozmoqda..." holati:** Xabar yuborilayotgan paytda Telegramda suhbatdoshga *'yozmoqda...'* (typing action) statusi ko'rinadi.
- **Daqiqalik Rate Limiter:** 
  - Bitta chat uchun: daqiqasiga ko'pi bilan 5 ta xabar.
  - Butun akkaunt bo'yicha (global): daqiqasiga ko'pi bilan 15 ta xabar.
  - Limit oshganda xabar to'xtatiladi va adminga ogohlantirish yuboriladi.
- **Crash xabarnomasi:** Agar tizimda kutilmagan og'ir xatolik yuz bersa, agent qulashdan oldin boshqaruv botida sizga xatolik sababi haqida xabar beradi.

---

## ⚡️ 6-BOSQICH: Xulosa, qidiruv, ovozli xabarlar va eslatmalar

6-bosqich loyihaning yakuniy bosqichi bo'lib, unga eng qulay va aqlli funksiyalar kiritildi:

### 1. Kunlik yozishmalar xulosasi (`/xulosa`)
- Bugun (so'nggi 24 soatda) kimlar bilan gaplashilgani, qanday muhim masalalar muhokama qilinganligi haqida Claude orqali qisqa, tushunarli **Executive Summary** tuzib beradi.
- Unda:
  - 👥 Gaplashilgan asosiy kontaktlar va mavzular;
  - 📌 Erishilgan kelishuvlar va natijalar;
  - ⏳ Kutilayotgan yoki ochiq qolgan masalalar;
  - 💡 Akkaunt egasi uchun amaliy eslatmalar aks etadi.

### 2. Yozishmalardan qidiruv (`/qidir <so'z>`)
- Saqlangan butun xabarlar bazasidan so'z yoki iborani bir zumda topib beradi.
- Misol:
  ```text
  /qidir shartnoma
  /qidir uchrashuv
  /qidir hisobot
  ```
- Natijalarda qidirilgan so'z tagiga chizilib, kim yozgani, chat va yuborilgan vaqti bilan birga keltiriladi.

### 3. Erkin matn buyruqlari
Boshqaruv botiga buyruq yozmasdan, oddiy insondek yozishingiz kifoya:
- *«Karimga ayt, ertaga borolmayman»*
- *«Sherzodga yoz, hisobotni jo'natdim»*
- *«Nodirga yetkaz, kechki soat 17:00 da gaplashamiz»*

**Qanday ishlaydi?**
1. Agent xabardan kimga yozish kerakligini (`Karim`) va maqsadni ajratib oladi.
2. Sizning uslubingizda (style samples) samimiy va chiroyli javob tayyorlaydi.
3. Boshqaruv botingizda tasdiqlash uchun chiqaradi:
   `[✅ Yuborish] [✏️ Tahrirlash] [❌ Bekor qilish]`
4. Siz `[✅ Yuborish]` ni bossangiz, xabar sizning akkauntingizdan Karimga jo'natiladi!

### 4. Ovozli xabarlarni matnga o'girish (Whisper STT)
- Suhbatdosh ovozli xabar (voice) yoki audio yuborganida:
  - Userbot faylni avtomatik `saved_media/` ga yuklab oladi.
  - Whisper API (OpenAI yoki Groq) orqali ovozni bir necha soniyada matnga o'giradi.
  - O'girilgan matn xabarlar tarixiga qo'shiladi va Claude orqali javob qoralamasi tayyorlanadi!
  - Boshqaruv botida sizga o'sha ovozli xabarning aniq transkripsiyasi va taklif etilgan javob ko'rinadi.

### 5. Javobsiz qolgan xabarlar eslatmasi (`/eslatma`)
- Sizga yozilgan, ammo 3 kundan beri (muddat `.env` da sozlanadi) javob berilmay qolib ketgan xabarlar bo'yicha ogohlantiradi.
- Fon xizmati har 12 soatda avtomatik tekshirib boradi (`reminder.py`).
- Istalgan vaqtda qo'lda tekshirish buyrug'i:
  ```text
  /eslatma      # Standart 3 kundan ortiq qolganlar
  /eslatma 5    # 5 kundan ortiq qolganlar
  ```

---

## ▶️ Qanday ishga tushirish va sinab ko'rish

1. Terminalda dasturni ishga tushiring:
```powershell
python main.py
```

2. **Boshqaruv botida yangi funksiyalarni sinash:**
- `/xulosa` — Bugungi yozishmalar tahlilini ko'rish.
- `/qidir salom` — Yozishmalar ichidan "salom" so'zini qidirish.
- `/eslatma` — Javob kutilayotgan xabarlar ro'yxatini ko'rish.
- **Erkin matn buyrug'i:** Boshqaruv botingizga shunchaki *"Karimga ayt, ertaga borolmayman"* deb yozib ko'ring. Agent uni tahlil qilib, Karimga yuboriladigan qoralamani tugmalar bilan taqdim etadi!
- **Ovozli xabar:** Biror kontakt sizga ovozli xabar yuborsin. Whisper sozlangan bo'lsa, xabar matnga o'girilib, javob taklif qilinadi.


