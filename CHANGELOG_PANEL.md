# VTP Panel Edition Changelog

## 4.3.0-vtp

- بازطراحی Wizard پنل مطابق مراحل اسکریپت اصلی VortexL2:
  - انتخاب نقش `IRAN` یا `KHAREJ`
  - تنظیم IP داخلی Tunnel، Port، RPC Port و Secret
  - وارد کردن Public IP سمت مقابل به‌عنوان Peer
  - مرحله Forward و دکمه نهایی **ذخیره و اجرا**
- تنظیم پیش‌فرض‌های IRAN/KHAREJ مطابق اسکریپت اصلی:
  - `IRAN`: IP داخلی `10.155.155.1`، hostname `iran`، Remote Forward IP برابر `10.155.155.2`
  - `KHAREJ`: IP داخلی `10.155.155.2`، hostname `kharej`، Remote Forward IP برابر `10.155.155.1`
- اضافه شدن default generator وابسته به نقش سرور، همراه با جلوگیری از conflict روی همان سرور.
- دکمه نهایی Wizard اکنون کانفیگ را ذخیره، systemd service را ایجاد و همان لحظه سرویس Tunnel را اجرا می‌کند.
- مسیر نصب مستقیم از GitHub برای ریپازیتوری `Unknown-sir/VTP` آماده شد.
- README کامل بازنویسی شد و شامل نصب، ورود به پنل، سناریوهای IRAN/KHAREJ، چند ایران، HAProxy و عیب‌یابی است.

## 4.2.0-vtp

- بخش‌بندی پنل به Dashboard، Wizard، Tunnel Management، Forwarding و Diagnostics.
- اصلاح نمایش EasyTier نصب‌شده از مسیرهای مختلف `PATH`.
- اصلاح رفتار HAProxy در حالت بدون listener.
- افزودن ابزار `vtp-doctor`.

## 4.1.0-vtp

- اضافه شدن پنل وب گرافیکی.
- اضافه شدن سرویس `vortexl2-panel.service`.
- پشتیبانی از چند Peer در EasyTier.
- یکتا شدن پورت، RPC port و interface برای چند Tunnel روی یک سرور.
