# 📋 REJALAR VA KELGUSI QADAMLAR (PLAN.MD)
**Loyiha:** Telegram Shaxsiy AI Agent tizimi  
**Oxirgi yangilanish vaqti:** 2026-09-27  
**Maqsad:** Agentni yanada mukammallashtirish, qulayliklarni kengaytirish va barqarorligini oshirish.

---

## 🚀 1. Yaqin Muddatli Vazifalar (Short-Term: 1–2 kun)
- [x] **Ovozli xabarlarni avtomatik matnga o'girish (STT - Speech-to-Text):**
  - Google Gemini Multimodal Audio va Whisper (Groq/OpenAI) integratsiyasi to'liq ishga tushirildi va sinovdan o'tkazildi. (Yakunlandi ✅)
- [ ] **Windows Avto-start (Doimiy fon rejimida ishlash):**
  - Kompyuter yonganda dastur avtomatik orqa fonda (yashirin) ishga tushishi uchun `run_agent.bat` yoki Windows Task Scheduler sozlamasini yaratish.
  - Kompyuter o'chib-yonishi bilan terminal ochib o'tirishga hojat qolmasligini ta'minlash.
- [ ] **Yozish uslubini kengaytirish (Telegram Chat Export):**
  - Telegram Desktop orqali o'zingizning haqiqiy do'stlaringiz bilan yozishmalaringiz eksport qilinganda, ulardan 50–100 ta eng xarakterli gaplaringizni ajratib olib [style_samples.json](file:///C:/Users/user/Desktop/Новая%20папка%20(8)/style_samples.json) ga qo'shish.

---

## ⚙️ 2. O'rta Muddatli Vazifalar (Medium-Term: 1–2 hafta)
- [ ] **Kontaktlar bo'yicha shaxsiy xotira (Contact Knowledge Base):**
  - Har bir suhbatdosh haqida muhim ma'lumotlarni alohida xotirada saqlash (masalan: *«Akmal - dasturchi, loyiha topshirish muddati 1-oktyabr»*, *«Sardor - tog'amning o'g'li»*).
  - AI javob tayyorlayotganda ushbu ma'lumotlarni inobatga olib, yanada chuqur va aniq gapirishini yo'lga qo'yish.
- [ ] **Ovozli javob qaytarish (TTS - Text-to-Speech):**
  - Agar suhbatdosh ovozli xabar yuborsa, bot javobni ham ovozli qilib (Voice note sifatida) tayyorlab, tasdiqlash uchun chiqarishi imkoniyati.
- [ ] **Boshqaruv boti uchun interaktiv asosiy menyu:**
  - `/start` bosilganda buyruqlarni yozib o'tirmasdan, qulay inline tugmalar orqali barcha holat va sozlamalarni bitta tugma bilan boshqarish.

---

## 🔮 3. Kengaytirilgan Imkoniyatlar (Advanced Features)
- [x] **Google Calendar / Taqvim integratsiyasi:**
  - Suhbatdosh bilan uchrashuv yoki sana kelishilganda, agent uni avtomatik aniqlab Google Calendar havolasi va `.ics` fayl tayyorlaydi. (Yakunlandi ✅)
- [x] **Hujjat va rasm/chek tahlili (Multimodal Vision):**
  - Telegram orqali yuborilgan to'lov cheklari, PDF va fotosuratlarni Gemini orqali chuqur tahlil qilish. (Yakunlandi ✅)
- [ ] **Web Dashboard (Veb-interfeys):**
  - Brauzer orqali barcha saqlangan xabarlar, statistika va AI parametrlarini vizual ko'rish paneli.

---

## 📌 Qoidalar va Eslatmalar:
1. Har bir yangi funksiya qo'shilganda yoki bajarilganda, `plan.md` dan [x] qilib o'chirilib, [done.md](file:///C:/Users/user/Desktop/Новая%20папка%20(8)/done.md) ga kiritib boriladi.
2. Har qanday o'zgarishda foydalanuvchi ma'lumotlarining daxlsizligi va xavfsizlik filtri birinchi o'rinda saqlanadi.
