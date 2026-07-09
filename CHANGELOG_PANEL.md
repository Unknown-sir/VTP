# Changelog

## 4.2.0-vtp

- طراحی مجدد پنل به‌صورت بخش‌بندی‌شده:
  - وضعیت کلی
  - ساخت Tunnel مرحله‌ای
  - مدیریت Tunnelها
  - Port Forwarding
  - عیب‌یابی و لاگ
- اضافه شدن Wizard مرحله‌ای برای ساخت Tunnel.
- اضافه شدن دکمه نصب خودکار EasyTier داخل پنل.
- اصلاح تشخیص EasyTier:
  - دیگر فقط مسیر `/usr/local/bin/easytier-core` بررسی نمی‌شود.
  - مسیرهای موجود در `PATH` هم بررسی می‌شوند.
  - در صورت نصب در مسیر دیگر، installer symlink می‌سازد.
- تقویت نصب EasyTier در `install.sh` با دو منبع دانلود fallback.
- اصلاح HAProxy:
  - اگر هیچ Forwarded Port وجود نداشته باشد، HAProxy دیگر با خطای no listener اجرا نمی‌شود.
  - پنل پیام واضح نشان می‌دهد که ابتدا باید Port تعریف شود.
- اضافه شدن aliasهای `vtp` و `vtp-doctor`.
- بروزرسانی README کامل برای نصب، استفاده از پنل، سناریوی خارج به چند ایران، HAProxy و عیب‌یابی.

## 4.1.0-panel

- اضافه شدن پنل وب اولیه.
- پشتیبانی از چند Peer در EasyTier.
- اضافه شدن `rpc_port` برای جلوگیری از conflict تونل دوم.
- اضافه شدن HAProxy generator جدید.
