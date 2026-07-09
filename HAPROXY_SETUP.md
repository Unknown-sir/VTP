# HAProxy در VTP

HAProxy برای Forward کردن پورت‌ها از سمت سرور به Backendهای داخل Tunnel استفاده می‌شود.

## فعال‌سازی

از داخل پنل وارد بخش **Port Forwarding** شوید و روی **فعال‌سازی HAProxy** کلیک کنید.

قبل از فعال‌سازی باید روی حداقل یک Tunnel این دو مقدار تنظیم شده باشد:

```text
Remote Forward IP
Forwarded ports
```

مثال:

```text
Remote Forward IP: 10.155.155.2
Forwarded ports: 80,443
```

## رفتار جدید در حالت بدون Listener

اگر هیچ پورت Forward تعریف نشده باشد، HAProxy نباید Start شود، چون HAProxy بدون listener با خطای زیر خارج می‌شود:

```text
Configuration file has no error but will not start (no listener)
```

در نسخه 4.2.0 این حالت خطا محسوب نمی‌شود. برنامه فایل کانفیگ را می‌نویسد، HAProxy را Stop نگه می‌دارد و داخل پنل پیام واضح نمایش می‌دهد.

## مسیر کانفیگ

```text
/etc/haproxy/haproxy.cfg
/etc/haproxy/vortexl2.cfg
```

## تست دستی کانفیگ

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
```

## لاگ

```bash
sudo journalctl -u haproxy -n 100 --no-pager
```
